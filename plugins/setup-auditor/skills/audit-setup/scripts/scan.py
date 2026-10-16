#!/usr/bin/env python3
"""Deterministic inventory and lint pass for a Claude Code setup.

Measures what loads into every session versus on demand, and flags
mechanical problems (broken imports, invalid JSON, vague skill
descriptions, dead path references, duplicated rules, exposed secrets).
Read-only. Standard library only.

Token counts are estimates: characters / 4, the common rule of thumb for
English prose. They are not tokenizer output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

CHARS_PER_TOKEN = 4
MAX_IMPORT_DEPTH = 5
LARGE_MEMORY_LINES = 200
MAX_DESCRIPTION_CHARS = 1536  # description + when_to_use are cut at this length in the skill listing
AGENT_DESCRIPTIONS_WARN_TOKENS = 15000  # Claude Code warns at startup above this combined size
AUTO_MEMORY_LINES, AUTO_MEMORY_BYTES = 200, 25_000  # how much of MEMORY.md loads each session
SKILL_FIELDS = {
    "name", "description", "when_to_use", "argument-hint", "arguments", "disable-model-invocation",
    "user-invocable", "allowed-tools", "disallowed-tools", "model", "effort", "context", "agent",
    "background", "hooks", "paths", "shell", "metadata", "license", "compatibility",
}
MIN_DESCRIPTION_CHARS = 40
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
SEVERITY_PENALTY = {"high": 15, "medium": 5, "low": 1, "info": 0}

TRIGGER_WORDS = re.compile(
    r"\b(use (it |this )?(when|for|whenever|before|after|to|at|on|in|if)\b|when(ever)? (the )?(user|you|asked|working)|trigger|invoke)\b",
    re.I,
)
VAGUE_LINES = re.compile(
    r"^\s*[-*]?\s*(always\s+)?(write (clean|good|readable|maintainable) code|follow best practices"
    r"|be careful|use common sense|keep (the )?code clean|make sure (the )?code is (good|clean|correct))\.?\s*$",
    re.I,
)
SECRET_PATTERNS = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI-style API key", re.compile(r"\bsk-(proj-)?[A-Za-z0-9]{32,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer/secret assignment", re.compile(
        r"(?i)\"?(api[_-]?key|secret|token|password|authorization)\"?\s*[:=]\s*\"?(bearer\s+)?[A-Za-z0-9_\-./+]{24,}")),
]
# Values that differ between otherwise identical rules: numbers (with $, %, decimals) and `code` spans.
VALUE_TOKEN = re.compile(r"`[^`\n]+`|\$?\b\d[\d,]*(?:\.\d+)?%?")
# Instruction files other agents read; they usually mirror CLAUDE.md and drift from it.
MIRROR_FILES = ("AGENTS.md", "GEMINI.md", ".cursorrules", ".windsurfrules", ".github/copilot-instructions.md")
MIRROR_GLOBS = (".cursor/rules/*.md", ".cursor/rules/*.mdc")
PATH_REF = re.compile(r"`((?:\.{1,2}/|~/|/)?[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+/?)`")


@dataclass
class Item:
    path: str
    kind: str
    scope: str
    loads: str  # "always" | "on-demand" | "conditional"
    chars: int
    lines: int
    note: str = ""

    @property
    def tokens(self) -> int:
        return round(self.chars / CHARS_PER_TOKEN)


@dataclass
class Finding:
    id: str
    severity: str
    path: str
    line: int
    message: str
    fix: str = ""


@dataclass
class Report:
    project_root: str
    home: str
    items: list[Item] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    mcp_servers: list[dict] = field(default_factory=list)
    hooks: list[dict] = field(default_factory=list)
    plugins: list[str] = field(default_factory=list)

    @property
    def always_tokens(self) -> int:
        return round(sum(i.chars for i in self.items if i.loads == "always") / CHARS_PER_TOKEN)

    @property
    def score(self) -> int:
        return max(0, 100 - sum(SEVERITY_PENALTY[f.severity] for f in self.findings))

    def add(self, *args, **kwargs) -> None:
        self.findings.append(Finding(*args, **kwargs))


# ---------------------------------------------------------------- helpers


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def display(path: Path, report: Report) -> str:
    p = str(path)
    if p.startswith(report.project_root + os.sep):
        return os.path.relpath(p, report.project_root)
    if p.startswith(report.home + os.sep):
        return "~" + p[len(report.home):]
    return p


def parse_frontmatter(text: str) -> tuple[dict | None, int]:
    """Parse simple YAML frontmatter. Returns (fields, body_start_line)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, 0
    fields: dict[str, str] = {}
    key = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return fields, i + 1
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            if value in (">", "|", ">-", "|-"):
                value = ""
            fields[key] = value.strip("\"'")
        elif key and line.startswith((" ", "\t")):
            fields[key] = (fields[key] + " " + line.strip().lstrip("- ")).strip()
    return None, 0


def strip_code_blocks(text: str) -> str:
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            out.append("")
            continue
        out.append("" if fenced else line)
    return "\n".join(out)


def load_json(path: Path, report: Report) -> dict | None:
    text = read_text(path)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        report.add("CSA001", "high", display(path, report), e.lineno,
                   f"Invalid JSON: {e.msg}. Claude Code will ignore or reject this file.",
                   "Fix the syntax error at the reported line.")
        return None
    return data if isinstance(data, dict) else None


def scan_secrets(path: Path, text: str, report: Report) -> None:
    for n, line in enumerate(text.splitlines(), start=1):
        for label, pat in SECRET_PATTERNS:
            if pat.search(line) and "${" not in line and "<" not in line:
                report.add("CSA011", "high", display(path, report), n,
                           f"Possible {label} stored in plain text (value not shown).",
                           "Move it to an environment variable or secret store, and rotate it if this file was ever committed or shared.")
                break


def git_ignored(path: Path, root: Path) -> bool | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", str(path)],
                           capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode == 128:
        return None  # not a git repo
    return r.returncode == 0


# ---------------------------------------------------------- memory files


def add_memory(path: Path, scope: str, report: Report, seen: set[Path], depth: int = 0,
               loads: str = "always", via: str = "") -> None:
    path = path.resolve()
    if path in seen:
        return
    text = read_text(path)
    if text is None:
        return
    seen.add(path)
    report.items.append(Item(display(path, report), "memory" if not via else "import", scope, loads,
                             len(text), text.count("\n") + 1, via))
    rel = display(path, report)
    lines = text.splitlines()

    if loads == "always" and len(lines) > LARGE_MEMORY_LINES:
        report.add("CSA009", "medium", rel, 1,
                   f"{len(lines)} lines load into every session (guidance: keep memory files under ~{LARGE_MEMORY_LINES}).",
                   "Move conditional sections into skills or path-scoped rules; delete what Claude can read from the code.")

    plain = strip_code_blocks(text)
    for n, line in enumerate(plain.splitlines(), start=1):
        if VAGUE_LINES.match(line):
            report.add("CSA012", "low", rel, n, f"Generic instruction with no testable meaning: \"{line.strip()}\".",
                       "Delete it, or replace it with the concrete rule you actually mean.")
        for m in re.finditer(r"(?:^|\s)@([~./A-Za-z0-9_\-][^\s`]*)", line):
            target_s = m.group(1).rstrip(".,;:)")
            if "/" not in target_s and "." not in target_s:
                continue  # @mention, not an import
            target = Path(os.path.expanduser(target_s))
            if not target.is_absolute():
                target = path.parent / target
            if not target.exists():
                report.add("CSA002", "high", rel, n, f"@import target not found: {target_s}",
                           "Fix the path or remove the import.")
            elif depth + 1 > MAX_IMPORT_DEPTH:
                report.add("CSA002", "medium", rel, n, f"@import nesting exceeds {MAX_IMPORT_DEPTH} levels; {target_s} will not load.",
                           "Flatten the import chain.")
            elif target.is_file():
                add_memory(target, scope, report, seen, depth + 1, loads, via=f"imported by {rel}")
        check_path_refs(path, n, line, report, relative_ok=scope != "user")

    scan_secrets(path, text, report)


def check_path_refs(path: Path, n: int, line: str, report: Report, relative_ok: bool = True) -> None:
    """User-level files describe every repo, so their relative paths are not checked."""
    for m in PATH_REF.finditer(line):
        ref = m.group(1)
        if any(c in ref for c in "*?<>{}$") or "://" in line[max(0, m.start() - 10):m.start()]:
            continue
        if not re.search(r"\.[A-Za-z0-9]{1,6}/?$|/$", ref):
            continue  # require a file extension or trailing slash to look like a path
        candidates = []
        expanded = Path(os.path.expanduser(ref))
        if expanded.is_absolute():
            candidates.append(expanded)
        elif relative_ok:
            candidates += [path.parent / ref, Path(report.project_root) / ref]
        else:
            continue
        if not any(c.exists() for c in candidates):
            report.add("CSA008", "medium", display(path, report), n,
                       f"Referenced path does not exist: {ref}",
                       "Update or remove the stale reference; Claude will otherwise act on a path that is not there.")


def memory_candidates(root: Path, home: Path) -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = [(home / ".claude" / "CLAUDE.md", "user")]
    chain = [root, *root.parents]
    for d in reversed(chain):
        if d == home or d == Path(d.anchor):
            continue
        scope = "project" if d == root else "ancestor"
        out += [(d / "CLAUDE.md", scope), (d / ".claude" / "CLAUDE.md", scope), (d / "CLAUDE.local.md", "local")]
    return out


def scan_rules(base: Path, scope: str, report: Report, seen: set[Path]) -> None:
    rules_dir = base / "rules"
    if not rules_dir.is_dir():
        return
    for f in sorted(rules_dir.rglob("*.md")):
        text = read_text(f) or ""
        fm, _ = parse_frontmatter(text)
        if fm and fm.get("paths"):
            report.items.append(Item(display(f, report), "rule", scope, "conditional", len(text),
                                     text.count("\n") + 1, f"paths: {fm['paths']}"))
            seen.add(f.resolve())
            scan_secrets(f, text, report)
        else:
            add_memory(f, scope, report, seen)


def scan_nested_memory(root: Path, report: Report) -> None:
    skip = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".next", "target"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        if Path(dirpath) == root:
            continue
        for name in ("CLAUDE.md", "CLAUDE.local.md"):
            if name in filenames:
                f = Path(dirpath) / name
                text = read_text(f) or ""
                report.items.append(Item(display(f, report), "memory", "nested", "on-demand", len(text),
                                         text.count("\n") + 1, "loads when Claude reads files in this directory"))
                scan_secrets(f, text, report)


# ------------------------------------------------------ skills and agents


def scan_definitions(base: Path, scope: str, report: Report, registry: dict[str, list[str]]) -> None:
    targets = [
        ("skill", sorted(base.glob("skills/*/SKILL.md"))),
        ("command", sorted(base.glob("commands/**/*.md"))),
        ("agent", sorted(base.glob("agents/**/*.md"))),
    ]
    for kind, files in targets:
        for f in files:
            text = read_text(f) or ""
            rel = display(f, report)
            fm, _ = parse_frontmatter(text)
            name = (fm or {}).get("name") or (f.parent.name if kind == "skill" else f.stem)
            desc = " ".join(filter(None, [(fm or {}).get("description", ""), (fm or {}).get("when_to_use", "")]))
            registry.setdefault(f"{kind}:{name}", []).append(rel)
            listing = len(name) + len(desc)
            user_only = (fm or {}).get("disable-model-invocation", "").lower() == "true"
            if user_only:
                report.items.append(Item(rel, kind, scope, "on-demand", listing, 1, "user-invoked only; not listed"))
            else:
                report.items.append(Item(rel, kind, scope, "always", listing, 1, "name + description listing"))
            report.items.append(Item(rel, kind + " body", scope, "on-demand", len(text) - listing,
                                     text.count("\n") + 1))
            scan_secrets(f, text, report)
            if fm is None and kind != "command":
                report.add("CSA003", "high", rel, 1, f"{kind.title()} has no parseable YAML frontmatter.",
                           "Add a --- block with at least name and description.")
                continue
            if kind == "skill":
                for key in sorted(set(fm or {}) - SKILL_FIELDS):
                    report.add("CSA016", "low", rel, 1, f"Frontmatter field '{key}' is not a documented skill field and is silently ignored.",
                               "Remove it, or move it under metadata: if it is information for humans.")
            if not desc:
                if kind != "command":
                    report.add("CSA003", "high", rel, 1, f"{kind.title()} has no description, so Claude cannot decide when to use it.",
                               "Add a description that says what it does and when to use it.")
                continue
            if len(desc) > MAX_DESCRIPTION_CHARS:
                report.add("CSA005", "medium", rel, 1,
                           f"Description is {len(desc)} chars (over {MAX_DESCRIPTION_CHARS}); it may be truncated and it costs context every session.",
                           "Cut it to what it does plus when to use it; move detail into the body.")
            elif len(desc) < MIN_DESCRIPTION_CHARS and kind != "command":
                report.add("CSA005", "medium", rel, 1, f"Description is only {len(desc)} chars; too little for reliable triggering.",
                           "Say what it does and when to use it, in words a user would type.")
            if kind in ("skill", "agent") and not user_only and not TRIGGER_WORDS.search(desc):
                report.add("CSA004", "medium", rel, 1,
                           "Description says what it is but not when to use it, so automatic triggering is unreliable.",
                           "Add a 'Use when …' clause naming the situations and phrases that should trigger it.")


def check_agent_budget(report: Report) -> None:
    agents = [i for i in report.items if i.kind == "agent" and i.loads == "always"]
    total = sum(i.tokens for i in agents)
    if total > AGENT_DESCRIPTIONS_WARN_TOKENS:
        report.add("CSA017", "high", agents[0].path, 1,
                   f"Subagent descriptions total ~{total:,} tokens (Claude Code warns above {AGENT_DESCRIPTIONS_WARN_TOKENS:,}).",
                   "Shorten descriptions to when-to-delegate only, and remove agents that are never used.")


def check_duplicates(report: Report, registry: dict[str, list[str]]) -> None:
    for key, paths in registry.items():
        if len(paths) > 1:
            kind, name = key.split(":", 1)
            report.add("CSA006", "medium", paths[0], 1,
                       f"{kind.title()} name '{name}' is defined {len(paths)} times: {', '.join(paths)}.",
                       "Keep one copy, or rename so it is clear which one runs.")

    seen: dict[str, tuple[str, int]] = {}
    for item in report.items:
        if item.kind not in ("memory", "import", "rule") or item.loads != "always":
            continue
        path = Path(item.path.replace("~", report.home, 1)) if item.path.startswith("~") else \
            Path(report.project_root, item.path) if not os.path.isabs(item.path) else Path(item.path)
        text = strip_code_blocks(read_text(path) or "")
        for n, line in enumerate(text.splitlines(), start=1):
            norm = re.sub(r"\W+", " ", line).strip().lower()
            if len(norm) < 40:
                continue
            if norm in seen and seen[norm][0] != item.path:
                other, other_line = seen[norm]
                report.add("CSA007", "medium", item.path, n,
                           f"Same instruction also loads from {other}:{other_line}; duplicates cost context twice and drift apart.",
                           "Keep it in the one scope where it belongs.")
            else:
                seen.setdefault(norm, (item.path, n))


def resolve_item(item: Item, report: Report) -> Path:
    if item.path.startswith("~"):
        return Path(report.home + item.path[1:])
    return Path(item.path) if os.path.isabs(item.path) else Path(report.project_root, item.path)


def collect_mirrors(root: Path, extra: list[Path], report: Report) -> list[Path]:
    """Instruction files Claude does not load but that should agree with what it does load."""
    known = {resolve_item(i, report).resolve() for i in report.items}
    found = [root / f for f in MIRROR_FILES] + [f for g in MIRROR_GLOBS for f in sorted(root.glob(g))]
    for p in extra:
        found += sorted(p.rglob("*.md")) if p.is_dir() else [p]
    out = []
    for f in found:
        f = f.resolve()
        if f.is_file() and f not in out and f not in known:
            out.append(f)
            text = read_text(f) or ""
            report.items.append(Item(display(f, report), "mirror", "mirror", "not loaded", len(text),
                                     text.count("\n") + 1, "compared for conflicting values only"))
    return out


def check_conflicting_values(report: Report, mirrors: list[Path]) -> None:
    """Flag rules worded the same in two files but carrying different numbers or `values`."""
    sources: list[tuple[Path, str, bool]] = []
    for item in report.items:
        path = resolve_item(item, report)
        if item.kind in ("memory", "import", "rule") and item.loads == "always":
            sources.append((path, item.path, True))
        elif item.kind == "memory" and item.loads == "not loaded" and path not in mirrors:
            sources.append((path, item.path, False))  # e.g. AGENTS.md ignored because CLAUDE.md exists
    sources += [(m, display(m, report), False) for m in mirrors]

    groups: dict[str, list[tuple[str, int, tuple[str, ...], bool, Path]]] = {}
    for path, rel, loaded in sources:
        for n, line in enumerate(strip_code_blocks(read_text(path) or "").splitlines(), start=1):
            values = tuple(v.strip("`") for v in VALUE_TOKEN.findall(line))
            if not values:
                continue
            key = re.sub(r"\W+", " ", VALUE_TOKEN.sub(" VALUE ", line)).strip().lower()
            if sum(1 for w in key.split() if w != "value" and w.isalpha()) < 3:
                continue  # too little wording to be sure two lines are the same rule
            groups.setdefault(key, []).append((rel, n, values, loaded, path))

    for rows in groups.values():
        reported: set[tuple[str, str]] = set()
        for i, (rel, n, values, loaded, path) in enumerate(rows):
            for orel, on, ovalues, oloaded, opath in rows[:i]:
                if orel == rel or ovalues == values or (orel, rel) in reported:
                    continue
                reported.add((orel, rel))
                a, b = path.stat().st_mtime, opath.stat().st_mtime
                newer = "same modification time" if abs(a - b) < 1 else \
                    f"{rel if a > b else orel} was modified more recently"
                report.add("CSA018", "high" if loaded and oloaded else "medium", rel, n,
                           f"Same rule, different values: {', '.join(values)} here vs {', '.join(ovalues)} in "
                           f"{orel}:{on} ({newer}). Each file looks right on its own.",
                           "Decide which value is current, keep the rule in one file, and rebuild any copy from it.")


# ------------------------------------------- settings, hooks, MCP, plugins


def scan_settings(path: Path, scope: str, report: Report) -> dict | None:
    data = load_json(path, report)
    text = read_text(path)
    if text is not None:
        scan_secrets(path, text, report)
    if data is None:
        return None
    rel = display(path, report)

    for event, groups in (data.get("hooks") or {}).items():
        for group in groups if isinstance(groups, list) else []:
            for hook in group.get("hooks", []) if isinstance(group, dict) else []:
                cmd = hook.get("command", "") if isinstance(hook, dict) else ""
                report.hooks.append({"file": rel, "event": event, "matcher": group.get("matcher", ""),
                                     "command": cmd[:120]})
                for tok in cmd.split()[:3]:
                    tok = tok.strip("\"'")
                    if tok.startswith(("/", "~/")) or tok.startswith("$CLAUDE_PROJECT_DIR"):
                        resolved = Path(os.path.expanduser(tok.replace("$CLAUDE_PROJECT_DIR", report.project_root)
                                                           .replace("${CLAUDE_PROJECT_DIR}", report.project_root)))
                        if "$" not in str(resolved) and not resolved.exists():
                            report.add("CSA014", "high", rel, 1,
                                       f"{event} hook runs a script that does not exist: {tok}",
                                       "Fix the path; a missing hook script fails on every matching event.")
                        break

    perms = data.get("permissions") or {}
    for rule in perms.get("allow", []) or []:
        if rule in ("Bash", "Bash(*)", "Bash(*:*)", "Edit", "Write", "*"):
            report.add("CSA015", "medium", rel, 1, f"Blanket allow rule '{rule}' skips every prompt for that tool.",
                       "Replace it with targeted rules for the commands this project actually runs.")

    for name in (data.get("enabledPlugins") or {}):
        if (data["enabledPlugins"] or {}).get(name):
            report.plugins.append(f"{name} ({scope})")

    for name, cfg in (data.get("mcpServers") or {}).items():
        report.mcp_servers.append({"name": name, "file": rel, "type": (cfg or {}).get("type", "stdio")})
    return data


def scan_mcp_file(path: Path, report: Report) -> None:
    data = load_json(path, report)
    text = read_text(path)
    if text is not None:
        scan_secrets(path, text, report)
    for name, cfg in ((data or {}).get("mcpServers") or {}).items():
        report.mcp_servers.append({"name": name, "file": display(path, report),
                                   "type": (cfg or {}).get("type", "stdio")})


def scan_user_mcp(home: Path, root: Path, report: Report) -> None:
    path = home / ".claude.json"
    if not path.is_file():
        return
    try:
        data = json.loads(read_text(path) or "{}")
    except json.JSONDecodeError:
        return  # internal state file; not the user's to hand-edit
    for name, cfg in (data.get("mcpServers") or {}).items():
        report.mcp_servers.append({"name": name, "file": "~/.claude.json (user)", "type": (cfg or {}).get("type", "stdio")})
    proj = (data.get("projects") or {}).get(str(root)) or {}
    for name, cfg in (proj.get("mcpServers") or {}).items():
        report.mcp_servers.append({"name": name, "file": "~/.claude.json (local)", "type": (cfg or {}).get("type", "stdio")})


def check_gitignore(root: Path, report: Report) -> None:
    for name in (".claude/settings.local.json", "CLAUDE.local.md"):
        f = root / name
        if f.exists() and git_ignored(f, root) is False:
            report.add("CSA010", "medium", name, 1, f"{name} is personal config but is not gitignored.",
                       f"Add {name} to .gitignore.")


# ------------------------------------------------------------------ main


def scan(root: Path, home: Path, include_user: bool, mirrors: list[Path] | None = None) -> Report:
    report = Report(str(root), str(home))
    seen: set[Path] = set()
    registry: dict[str, list[str]] = {}

    for path, scope in memory_candidates(root, home):
        if scope == "user" and not include_user:
            continue
        if path.is_file():
            add_memory(path, scope, report, seen)
    if include_user:
        scan_rules(home / ".claude", "user", report, seen)
    scan_rules(root / ".claude", "project", report, seen)
    scan_nested_memory(root, report)

    agents_md = root / "AGENTS.md"
    if agents_md.is_file() and agents_md.resolve() not in seen:
        has_claude_md = any(i.kind == "memory" and i.scope in ("project", "ancestor", "local") for i in report.items)
        if has_claude_md:
            text = read_text(agents_md) or ""
            report.items.append(Item("AGENTS.md", "memory", "project", "not loaded", len(text), text.count("\n") + 1,
                                     "ignored because a CLAUDE.md exists; add @AGENTS.md to CLAUDE.md if it should apply"))
        else:
            add_memory(agents_md, "project", report, seen)

    if include_user:
        slug = re.sub(r"[^A-Za-z0-9]", "-", str(root))
        mem = home / ".claude" / "projects" / slug / "memory" / "MEMORY.md"
        text = read_text(mem)
        if text is not None:
            head = "\n".join(text.splitlines()[:AUTO_MEMORY_LINES])[:AUTO_MEMORY_BYTES]
            report.items.append(Item(display(mem, report), "auto memory", "user", "always", len(head),
                                     head.count("\n") + 1, f"first {AUTO_MEMORY_LINES} lines / 25KB load each session"))
            scan_secrets(mem, text, report)

    if include_user:
        scan_definitions(home / ".claude", "user", report, registry)
    scan_definitions(root / ".claude", "project", report, registry)
    check_duplicates(report, registry)
    check_agent_budget(report)
    check_conflicting_values(report, collect_mirrors(root, mirrors or [], report))

    if include_user:
        scan_settings(home / ".claude" / "settings.json", "user", report)
        scan_user_mcp(home, root, report)
    for name, scope in (("settings.json", "project"), ("settings.local.json", "local")):
        f = root / ".claude" / name
        if f.is_file():
            scan_settings(f, scope, report)
    if (root / ".mcp.json").is_file():
        scan_mcp_file(root / ".mcp.json", report)
    check_gitignore(root, report)

    report.findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.path, f.line))
    return report


def render(report: Report) -> str:
    total_chars = sum(i.chars for i in report.items if i.loads == "always")
    out = [
        "# Claude setup scan",
        "",
        f"Project: `{report.project_root}`",
        "",
        f"**Mechanical health: {report.score}/100** (100 minus 15 per high, 5 per medium, 1 per low finding).",
        "",
        f"**Always-loaded instruction context: ~{report.always_tokens:,} tokens** ({total_chars:,} chars, estimated as chars/4; "
        "excludes Claude Code's own system prompt, MCP tool schemas and plugin listings, which this scan cannot measure).",
        "",
        "## Context by file",
        "",
        "| Loads | Scope | Kind | File | Lines | ~Tokens | Note |",
        "|---|---|---|---|---:|---:|---|",
    ]
    order = {"always": 0, "conditional": 1, "on-demand": 2, "not loaded": 3}
    for i in sorted(report.items, key=lambda i: (order.get(i.loads, 9), -i.chars)):
        if i.kind.endswith(" body") and i.chars < 1:
            continue
        lines = "" if i.kind in ("skill", "agent", "command") else str(i.lines)
        out.append(f"| {i.loads} | {i.scope} | {i.kind} | `{i.path}` | {lines} | {i.tokens:,} | {i.note} |")
    if not report.items:
        out.append("| — | — | — | no Claude configuration found | | | |")

    out += ["", "## Findings", ""]
    if report.findings:
        counts = {s: sum(1 for f in report.findings if f.severity == s) for s in SEVERITY_ORDER}
        out.append(", ".join(f"{n} {s}" for s, n in counts.items() if n))
        out.append("")
        for f in report.findings:
            out.append(f"- **[{f.severity}] {f.id}** `{f.path}:{f.line}` — {f.message}" + (f" *Fix:* {f.fix}" if f.fix else ""))
    else:
        out.append("No mechanical problems found.")

    out += ["", "## Integrations", ""]
    out.append("MCP servers (tools are deferred behind tool search by default, so each costs little until used): " + (", ".join(f"`{m['name']}` ({m['type']}, {m['file']})" for m in report.mcp_servers) or "none configured"))
    out.append("")
    out.append("Enabled plugins: " + (", ".join(f"`{p}`" for p in report.plugins) or "none recorded in settings"))
    out.append("")
    if report.hooks:
        out.append("Hooks:")
        for h in report.hooks:
            out.append(f"- {h['event']} `{h['matcher'] or '*'}` → `{h['command']}` ({h['file']})")
    else:
        out.append("Hooks: none")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", nargs="?", default=".", help="project directory to scan (default: .)")
    ap.add_argument("--home", default=os.path.expanduser("~"), help="home directory holding .claude/ (default: ~)")
    ap.add_argument("--no-user", action="store_true", help="skip user-level ~/.claude configuration")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    ap.add_argument("--mirror", action="append", default=[], metavar="PATH",
                    help="extra file or directory of copies to check for conflicting values (repeatable)")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any high-severity finding exists (for CI)")
    args = ap.parse_args(argv)

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    report = scan(root, Path(args.home).expanduser().resolve(), not args.no_user,
                  [Path(m).expanduser().resolve() for m in args.mirror])
    if args.json:
        data = asdict(report)
        data["always_loaded_tokens_estimate"] = report.always_tokens
        data["score"] = report.score
        print(json.dumps(data, indent=2))
    else:
        sys.stdout.write(render(report))
    if args.strict and any(f.severity == "high" for f in report.findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

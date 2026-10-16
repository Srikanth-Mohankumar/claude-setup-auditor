# Setup Auditor for Claude Code

**Find out what your Claude Code setup actually costs every session, and what is quietly broken in it.**

CLAUDE.md files grow, skills stop triggering, hooks point at scripts that were deleted months
ago, and a teammate's `"allow": ["Bash"]` sits in the shared settings. Nobody re-reads any of it.
`setup-auditor` does that for you:

- **Measures** how many tokens your CLAUDE.md, rules, skills, agents and auto memory load into
  *every* session, file by file, and what loads only on demand.
- **Detects** 17 kinds of mechanical problems deterministically, with no model guessing involved:
  broken `@imports`, dead paths, invalid JSON, vague skill descriptions, duplicate rules across
  scopes, copies of a rule whose numbers have drifted apart, missing hook scripts, blanket permissions and plain-text secrets.
- **Reviews** what a script can't judge, against the *current* Claude Code docs rather than model
  memory. For example: is this instruction true, does Claude need it, will this skill fire on the
  prompt you'd type?
- **Fixes** the setup only when you ask, on its own git branch, one commit per area, with undo
  instructions.

## Quick start

```text
/plugin marketplace add Srikanth-Mohankumar/claude-setup-auditor
/plugin install setup-auditor@srikanth-claude-tools
```

```text
/setup-auditor:audit-setup              # read-only audit of this project + ~/.claude
/setup-auditor:audit-setup ./backend    # audit another directory
/setup-auditor:fix-setup                # apply the fixes on a reviewable branch
```

## What a scan finds

These are real scanner findings from a small demo project with typical drift, condensed from the Markdown report:

```text
Mechanical health: 18/100 (100 minus 15 per high, 5 per medium, 1 per low finding).
Always-loaded instruction context: ~169 tokens (676 chars, estimated as chars/4)

2 high, 10 medium, 2 low

[high]   CSA014 .claude/settings.json — PostToolUse hook runs a script that does not exist:
         $CLAUDE_PROJECT_DIR/.claude/hooks/format.sh
[high]   CSA002 CLAUDE.md:14 — @import target not found: docs/architecture.md
[medium] CSA015 .claude/settings.json — Blanket allow rule 'Bash' skips every prompt for that tool.
[medium] CSA004 .claude/skills/pdf-export/SKILL.md — Description says what it is but not when
         to use it, so automatic triggering is unreliable.
[medium] CSA008 CLAUDE.md:11 — Referenced path does not exist: lib/http.ts
[medium] CSA007 CLAUDE.md:12 — Same instruction also loads from ~/.claude/CLAUDE.md:1
[medium] CSA006 Skill name 'release' is defined 2 times (user and project scope)
[medium] CSA010 .claude/settings.local.json is personal config but is not gitignored.
[low]    CSA016 .claude/skills/pdf-export/SKILL.md — 'version' is not a documented skill field
[low]    CSA012 CLAUDE.md:10 — Generic instruction with no testable meaning: "Write clean code"
...
```

The audit skill builds on this with the judgment calls. On the same demo it noticed that the
`release` skill pushes tags and could be invoked automatically under a blanket `Bash` allow.
It also found that the `reviewer` agent is told to "review the diff" but has no tool that can
run `git diff`. For each skill description it rewrote, it gave an example prompt the new
description should match.

`fix-setup` then cleared every project-level finding in five commits (the project-only score is
now 100/100). The one finding left is the duplicate `release` skill in `~/.claude`. That is a
user-level file, so fix-setup proposed the change instead of making it:

```text
fdc34a0 Fix broken Claude config: dead import, stale paths, missing hook
eef5d31 Trim always-loaded CLAUDE.md
18327a2 Drop unverifiable commands from CLAUDE.md
b52c7b5 Make skill and agent triggering reliable; gate release to manual use
91df663 Replace blanket Bash allow with targeted rules; gitignore local settings
```

## How it works

| Layer | What | Why |
|---|---|---|
| `scan.py` | Standard-library Python. Inventories every scope, estimates context per file, runs 17 checks. About 0.1s, no network. | Numbers and broken references should be facts, not model estimates. |
| `audit-setup` skill | Runs the scanner, fetches current docs, reviews against a [checklist](plugins/setup-auditor/skills/audit-setup/references/checklist.md), and returns a fixed-format report. **Read-only.** | Judgment such as "is this true", "will this trigger" or "should this be a hook" needs a model, grounded in evidence. |
| `fix-setup` skill | Runs only when you type it. Applies fixes on a branch, then re-scans to verify. | Changes you can review in `git diff` and undo with one command. |

### What counts as "always loaded"

The scanner follows the current [memory](https://code.claude.com/docs/en/memory),
[skills](https://code.claude.com/docs/en/skills) and
[sub-agents](https://code.claude.com/docs/en/sub-agents) docs:

| Always loaded | Loaded on demand |
|---|---|
| `~/.claude/CLAUDE.md`, project and ancestor `CLAUDE.md` / `.claude/CLAUDE.md` / `CLAUDE.local.md` | `CLAUDE.md` in subdirectories |
| Everything they `@import` | `.claude/rules/*.md` with `paths:` |
| `.claude/rules/*.md` without `paths:` (user and project) | Skill and agent bodies |
| Skill and agent **name + description** | Skills with `disable-model-invocation: true` |
| First 200 lines / 25KB of auto-memory `MEMORY.md` | MCP tool schemas (deferred by tool search) |
| `AGENTS.md`, only when no `CLAUDE.md` exists | |

Token counts are **estimates** (characters ÷ 4), not tokenizer output. They don't include Claude
Code's own system prompt or plugin skill listings.

### Checks

| ID | Severity | Finds |
|---|---|---|
| CSA001 | high | Settings or `.mcp.json` that isn't valid JSON |
| CSA002 | high | `@import` targets that don't exist, or nest too deep |
| CSA003 | high | Skills/agents with no frontmatter or no description |
| CSA004 | medium | Descriptions that never say *when* to use the skill/agent |
| CSA005 | medium | Descriptions too short to trigger, or over the 1,536-char listing cut-off |
| CSA006 | medium | Same skill/agent/command name defined in more than one scope |
| CSA007 | medium | The same instruction loaded from two files |
| CSA008 | medium | Paths referenced in CLAUDE.md/rules that don't exist |
| CSA009 | medium | Always-loaded memory files over ~200 lines |
| CSA010 | medium | `settings.local.json` / `CLAUDE.local.md` not gitignored |
| CSA011 | high | API keys, tokens or private keys in config (the value is never printed) |
| CSA012 | low | Instructions with no testable meaning ("write clean code") |
| CSA014 | high | Hooks that run a script that doesn't exist |
| CSA015 | medium | Blanket allow rules (`Bash`, `Edit`, `*`) |
| CSA016 | low | Undocumented SKILL.md frontmatter fields, which are silently ignored |
| CSA017 | high | Subagent descriptions over Claude Code's 15k-token warning |
| CSA018 | high / medium | The same rule in two copies with different numbers or `values` (high when Claude loads both) |

### Copies that drift

Rules often live in more than one place: CLAUDE.md and AGENTS.md, a backup, or skill folders
mirrored for several tools. Each copy can look right on its own while the numbers have drifted
apart. CSA018 compares every copy and names which file changed more recently. It doesn't guess
which one is correct.

Other agents' instruction files are checked automatically. These are AGENTS.md, GEMINI.md, and
the Cursor, Copilot and Windsurf rules. Point the scanner at any other copies yourself:

```bash
python3 scan.py . --mirror docs/rules-backup.md --mirror .cursor/skills
```

The check matches rules whose wording is the same apart from the values. It doesn't catch a
copy whose wording was also rewritten.

## Use it in CI

`scan.py` is a single standalone file that runs without Claude Code. Copy it into your repo or clone this one, then run it in a pre-commit hook or a pipeline:

```bash
python3 plugins/setup-auditor/skills/audit-setup/scripts/scan.py . --no-user --strict
```

`--strict` exits 1 on any high-severity finding. `--json` gives machine-readable output.

## Safety

- `audit-setup` never edits, creates or deletes files.
- `fix-setup` runs only when you type it (`disable-model-invocation: true`). It stops on a dirty
  tree or outside git and works on a `setup-audit/<date>` branch. It never pushes or rewrites
  history, and never weakens deny rules or security hooks. It asks before editing user-level
  `~/.claude` files, and backs each one up first.
- Secrets that are found are reported by file and line only, never echoed.

## Cost

The scanner is free. The skills are ordinary Claude Code sessions. As one data point, each was
run once headless on the demo project above, in a home directory with 22 user-level skills,
using Opus 5.5:

- audit: 16 turns, about $1.49
- fix: 31 turns, about $2.23

Larger setups cost more. Treat these as single runs, not benchmarks.

## Development

```bash
python3 -m unittest discover tests     # scanner tests, one planted problem per fixture
claude plugin validate .               # manifest validation
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT

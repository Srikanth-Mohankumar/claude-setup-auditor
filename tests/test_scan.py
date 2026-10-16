"""Tests for the audit-setup scanner.

Each test builds a throwaway project + home directory with one planted
problem and asserts the scanner reports it. The clean fixture asserts the
scanner stays quiet on a healthy setup. Run: python3 -m unittest discover tests
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

# Keep the developer's global gitignore and git config out of the results.
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "XDG_CONFIG_HOME": os.devnull}

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/setup-auditor/skills/audit-setup/scripts/scan.py"

GOOD_SKILL = """\
---
name: deploy-check
description: Checks a release branch before deploy. Use when the user asks whether a branch is ready to ship.
---
Run the checks.
"""


def write(base: Path, rel: str, text: str) -> Path:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


class ScanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.root = base / "project"
        self.home = base / "home"
        self.root.mkdir()
        (self.home / ".claude").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def scan(self, *extra):
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(self.root), "--home", str(self.home), "--json", *extra],
                           capture_output=True, text=True, check=False, env=ENV)
        self.assertIn(r.returncode, (0, 1), r.stderr)
        self.returncode = r.returncode
        return json.loads(r.stdout)

    def ids(self, data):
        return [f["id"] for f in data["findings"]]

    # -- healthy setup

    def test_clean_setup_has_no_findings(self):
        write(self.root, "CLAUDE.md", "# Project\n\nRun tests with `make test`.\n")
        write(self.root, "Makefile", "test:\n\ttrue\n")
        write(self.root, ".claude/skills/deploy-check/SKILL.md", GOOD_SKILL)
        write(self.root, ".claude/settings.json", '{"permissions": {"allow": ["Bash(make test)"]}}')
        data = self.scan()
        self.assertEqual(data["findings"], [])
        self.assertEqual(data["score"], 100)
        self.assertGreater(data["always_loaded_tokens_estimate"], 0)

    # -- context accounting

    def test_counts_always_loaded_vs_on_demand(self):
        write(self.home, ".claude/CLAUDE.md", "x" * 400)
        write(self.root, "CLAUDE.md", "y" * 800)
        write(self.root, "sub/CLAUDE.md", "z" * 4000)
        write(self.root, ".claude/rules/api.md", "---\npaths: src/api/**\n---\n" + "w" * 4000)
        data = self.scan()
        loads = {i["path"]: i["loads"] for i in data["items"]}
        self.assertEqual(loads["sub/CLAUDE.md"], "on-demand")
        self.assertEqual(loads[".claude/rules/api.md"], "conditional")
        self.assertEqual(data["always_loaded_tokens_estimate"], round(1200 / 4))

    def test_paths_list_form_is_conditional(self):
        write(self.root, ".claude/rules/api.md", '---\npaths:\n  - "src/api/**"\n---\nValidate input.\n')
        data = self.scan()
        self.assertEqual({i["path"]: i["loads"] for i in data["items"]}[".claude/rules/api.md"], "conditional")

    def test_imports_are_counted_and_broken_ones_flagged(self):
        write(self.root, "CLAUDE.md", "See @docs/guide.md and @docs/missing.md\n")
        write(self.root, "docs/guide.md", "g" * 400)
        data = self.scan()
        self.assertIn("docs/guide.md", [i["path"] for i in data["items"] if i["loads"] == "always"])
        self.assertEqual(self.ids(data), ["CSA002"])

    def test_user_only_skill_costs_no_listing(self):
        write(self.root, ".claude/skills/fix/SKILL.md",
              "---\nname: fix\ndescription: Applies fixes.\ndisable-model-invocation: true\n---\nbody\n")
        data = self.scan()
        listing = [i for i in data["items"] if i["kind"] == "skill"]
        self.assertEqual(listing[0]["loads"], "on-demand")
        self.assertNotIn("CSA004", self.ids(data))

    def test_agents_md_ignored_when_claude_md_exists(self):
        write(self.root, "CLAUDE.md", "# P\n")
        write(self.root, "AGENTS.md", "# A\n")
        data = self.scan()
        self.assertEqual({i["path"]: i["loads"] for i in data["items"]}["AGENTS.md"], "not loaded")

    def test_agents_md_loaded_without_claude_md(self):
        write(self.root, "AGENTS.md", "# A\n")
        data = self.scan()
        self.assertEqual({i["path"]: i["loads"] for i in data["items"]}["AGENTS.md"], "always")

    def test_auto_memory_index_counts(self):
        slug = "".join(c if c.isalnum() else "-" for c in str(self.root.resolve()))
        write(self.home, f".claude/projects/{slug}/memory/MEMORY.md", "- [a](a.md) — hook\n" * 300)
        data = self.scan()
        mem = [i for i in data["items"] if i["kind"] == "auto memory"]
        self.assertEqual(mem[0]["lines"], 200)

    # -- planted problems

    def test_invalid_settings_json(self):
        write(self.root, ".claude/settings.json", '{"permissions": {"allow": ["Bash(ls)",]}}')
        self.assertEqual(self.ids(self.scan()), ["CSA001"])

    def test_skill_without_frontmatter(self):
        write(self.root, ".claude/skills/bare/SKILL.md", "Just do the thing.\n")
        self.assertEqual(self.ids(self.scan()), ["CSA003"])

    def test_skill_description_without_trigger(self):
        write(self.root, ".claude/skills/pdf/SKILL.md",
              "---\nname: pdf\ndescription: Handles PDF files including merging, splitting and rotating pages.\n---\nbody\n")
        self.assertEqual(self.ids(self.scan()), ["CSA004"])

    def test_when_to_use_counts_as_trigger(self):
        write(self.root, ".claude/skills/pdf/SKILL.md",
              "---\nname: pdf\ndescription: Handles PDF files including merging and splitting.\n"
              "when_to_use: Use when the user mentions a .pdf file.\n---\nbody\n")
        self.assertEqual(self.ids(self.scan()), [])

    def test_description_too_long_and_too_short(self):
        write(self.root, ".claude/skills/long/SKILL.md", f"---\nname: long\ndescription: Use when {'x' * 1600}\n---\n")
        write(self.root, ".claude/skills/short/SKILL.md", "---\nname: short\ndescription: Use when asked.\n---\n")
        self.assertEqual(sorted(self.ids(self.scan())), ["CSA005", "CSA005"])

    def test_duplicate_skill_names_across_scopes(self):
        write(self.home, ".claude/skills/deploy-check/SKILL.md", GOOD_SKILL)
        write(self.root, ".claude/skills/deploy-check/SKILL.md", GOOD_SKILL)
        self.assertEqual(self.ids(self.scan()), ["CSA006"])

    def test_duplicate_instruction_across_files(self):
        rule = "Always run the full integration suite before opening a pull request.\n"
        write(self.home, ".claude/CLAUDE.md", rule)
        write(self.root, "CLAUDE.md", rule)
        self.assertEqual(self.ids(self.scan()), ["CSA007"])

    def test_dead_path_reference(self):
        write(self.root, "CLAUDE.md", "Config lives in `config/app.yaml` and `src/main.py`.\n")
        write(self.root, "src/main.py", "")
        data = self.scan()
        self.assertEqual(self.ids(data), ["CSA008"])
        self.assertIn("config/app.yaml", data["findings"][0]["message"])

    def test_user_level_relative_paths_not_checked(self):
        write(self.home, ".claude/CLAUDE.md", "In repos with `.agents/skills/`, that copy is canonical.\n")
        self.assertEqual(self.ids(self.scan()), [])

    def test_large_memory_file(self):
        write(self.root, "CLAUDE.md", "".join(f"- rule {n}\n" for n in range(250)))
        self.assertEqual(self.ids(self.scan()), ["CSA009"])

    def test_vague_instruction(self):
        write(self.root, "CLAUDE.md", "# Style\n\n- Write clean code\n")
        self.assertEqual(self.ids(self.scan()), ["CSA012"])

    def test_local_settings_not_gitignored(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True, env=ENV)
        write(self.root, ".claude/settings.local.json", "{}")
        self.assertEqual(self.ids(self.scan()), ["CSA010"])
        write(self.root, ".gitignore", ".claude/settings.local.json\n")
        self.assertEqual(self.ids(self.scan()), [])

    def test_secret_is_flagged_and_not_echoed(self):
        fake = "sk-ant-" + "a1B2" * 10  # assembled so the repo never contains a key-shaped literal
        write(self.root, ".mcp.json", json.dumps({"mcpServers": {"x": {"command": "x", "env": {"KEY": fake}}}}))
        data = self.scan()
        self.assertEqual(self.ids(data), ["CSA011"])
        self.assertNotIn(fake, json.dumps(data["findings"]))

    def test_secret_via_env_reference_is_fine(self):
        write(self.root, ".mcp.json", json.dumps({"mcpServers": {"x": {"command": "x", "env": {"KEY": "${API_KEY}"}}}}))
        data = self.scan()
        self.assertEqual(self.ids(data), [])
        self.assertEqual(data["mcp_servers"][0]["name"], "x")

    def test_missing_hook_script(self):
        write(self.root, ".claude/settings.json", json.dumps({"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/guard.sh"}]}]}}))
        self.assertEqual(self.ids(self.scan()), ["CSA014"])
        write(self.root, ".claude/hooks/guard.sh", "#!/bin/sh\n")
        self.assertEqual(self.ids(self.scan()), [])

    def test_blanket_allow(self):
        write(self.root, ".claude/settings.json", '{"permissions": {"allow": ["Bash"]}}')
        self.assertEqual(self.ids(self.scan()), ["CSA015"])

    def test_unknown_skill_field(self):
        write(self.root, ".claude/skills/deploy-check/SKILL.md", GOOD_SKILL.replace("---\nRun", "version: 1.0.0\n---\nRun"))
        self.assertEqual(self.ids(self.scan()), ["CSA016"])

    def test_agent_description_budget(self):
        for n in range(12):
            write(self.root, f".claude/agents/a{n}.md", f"---\nname: a{n}\ndescription: Use when {'d' * 6000}\n---\n")
        self.assertIn("CSA017", self.ids(self.scan()))

    def test_score_penalises_by_severity(self):
        write(self.root, ".claude/settings.json", "{")  # high
        write(self.root, ".claude/skills/bare/SKILL.md", "---\nname: bare\ndescription: Does a thing to files.\n---\n")  # medium
        self.assertEqual(self.scan()["score"], 100 - 15 - 5 - 5)  # too short + no trigger

    # -- conflicting values (CSA018). Scenario from a reader: a working copy and a backup of the
    # same rules drifted; updates landed in the backup, and each file looked right on its own.

    def test_conflicting_value_in_declared_mirror(self):
        write(self.root, "CLAUDE.md", "Quote the enterprise discount as 15% for annual plans.\n")
        backup = write(self.root, "backup/rules.md", "Quote the enterprise discount as 20% for annual plans.\n")
        os.utime(self.root / "CLAUDE.md", (1_700_000_000, 1_700_000_000))
        os.utime(backup, (1_800_000_000, 1_800_000_000))
        data = self.scan("--mirror", str(self.root / "backup"))
        self.assertEqual(self.ids(data), ["CSA018"])
        f = data["findings"][0]
        self.assertEqual(f["severity"], "medium")
        self.assertIn("20%", f["message"])
        self.assertIn("15%", f["message"])
        self.assertIn("backup/rules.md was modified more recently", f["message"])

    def test_undeclared_backup_is_not_scanned(self):
        write(self.root, "CLAUDE.md", "Quote the enterprise discount as 15% for annual plans.\n")
        write(self.root, "backup/rules.md", "Quote the enterprise discount as 20% for annual plans.\n")
        self.assertEqual(self.ids(self.scan()), [])

    def test_conflict_between_two_loaded_files_is_high(self):
        write(self.home, ".claude/CLAUDE.md", "Keep pull requests under 400 changed lines.\n")
        write(self.root, "CLAUDE.md", "Keep pull requests under 250 changed lines.\n")
        data = self.scan()
        self.assertEqual(self.ids(data), ["CSA018"])
        self.assertEqual(data["findings"][0]["severity"], "high")

    def test_agents_md_mirror_with_different_command(self):
        write(self.root, "CLAUDE.md", "Install dependencies with `pnpm install` before running tests.\n")
        write(self.root, "AGENTS.md", "Install dependencies with `npm install` before running tests.\n")
        data = self.scan()
        self.assertEqual(self.ids(data), ["CSA018"])
        self.assertIn("npm install", data["findings"][0]["message"])

    def test_identical_mirror_is_fine(self):
        rule = "Quote the enterprise discount as 15% for annual plans.\n"
        write(self.root, "CLAUDE.md", rule)
        write(self.root, ".github/copilot-instructions.md", rule)
        self.assertEqual(self.ids(self.scan()), [])

    def test_short_or_same_file_values_are_not_conflicts(self):
        write(self.root, "CLAUDE.md", "- Step 1\n- Step 2\nRetry failed uploads 3 times.\nRetry failed uploads 5 times.\n")
        write(self.root, "GEMINI.md", "- Step 3\n")
        self.assertEqual(self.ids(self.scan()), [])

    def test_strict_exit_code(self):
        write(self.root, ".claude/settings.json", "{")
        self.scan("--strict")
        self.assertEqual(self.returncode, 1)


if __name__ == "__main__":
    unittest.main()

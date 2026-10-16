# Changelog

All notable changes to this project will be documented here.

## [2.1.0] - 2026-10-16

### Added
- CSA018: flags the same rule in two copies with different numbers or `code` values, and names
  the file that changed more recently. Copies are other agents' instruction files (AGENTS.md,
  GEMINI.md, and the Cursor, Copilot and Windsurf rules), found automatically, plus any path given
  with the new `--mirror` option. Suggested by a reader whose backup copy of a rulebook drifted
  from the working copy.

## [2.0.0] - 2026-10-14

### Changed
- **Renamed the plugin to `setup-auditor`.** `claude plugin validate` rejects plugin names
  starting with `claude-`. Reinstall with `/plugin install setup-auditor@srikanth-claude-tools`;
  commands are now `/setup-auditor:audit-setup` and `/setup-auditor:fix-setup`. The marketplace
  declares the rename in `renames`, so existing installs can migrate.
- `audit-setup` now runs the scanner first and returns a fixed-format report with a health score,
  always-loaded token budget, top-fixes table and example trigger prompts. It is still read-only.
- Skill frontmatter follows current docs: `version` moved under `metadata`, and `allowed-tools`
  is scoped to the bundled script.

### Added
- `scan.py`: a standard-library scanner that estimates context per file across every scope and
  runs 16 deterministic checks (CSA001–CSA017). Supports `--json` and `--strict` for CI.
- `fix-setup`: a user-invoked skill that applies fixes on a `setup-audit/<date>` branch, one commit
  per area. It asks before and backs up any user-level edit, then re-scans to verify.
- A review checklist that names the docs page behind each rule.
- Scanner unit tests.

## [1.0.0] - 2026-09-30

### Added
- Initial public release.
- Read-only Claude Code setup audit skill.
- Current plugin manifest and marketplace metadata.
- Review of CLAUDE.md, rules, skills, agents, hooks, settings, MCP/plugin usage, and context overhead.
- Prioritized file-level recommendations grounded in current Claude Code documentation.
- Skill/agent trigger review with example prompts.

# Claude Setup Auditor

Keep your Claude Code setup lean, current, and useful.

`claude-setup-auditor` is an autonomous Claude Code plugin that audits your project and user-level Claude configuration against current Claude Code documentation, repairs stale or duplicated configuration, verifies the result, and reports the before/after always-loaded context footprint.

## Why this exists

Claude Code setups tend to accumulate over time:

- oversized or stale `CLAUDE.md` files
- duplicated rules
- skills that no longer trigger reliably
- subagents with overly broad tool access
- policy text that should be enforced with hooks
- unused MCP servers and plugins consuming context
- undocumented or unverified build/test commands

This plugin turns that maintenance into one repeatable audit.

## What it audits

- `CLAUDE.md`
- `CLAUDE.local.md`
- `AGENTS.md`
- `.claude/rules/`
- `.claude/skills/`
- `.claude/agents/`
- `.claude/commands/`
- `.claude/settings.json`
- `.claude/settings.local.json`
- `~/.claude/`
- hooks
- MCP servers
- installed plugins
- always-loaded vs on-demand context

## Safety model

The audit is intentionally autonomous, but changes are made to be recoverable:

- checks `git status` before editing
- stashes a dirty working tree and restores it afterwards
- works on a dated audit branch
- commits phase-by-phase
- backs up files outside the repository before editing
- does not write secrets or credentials into commit-able files
- does not use `sudo`
- does not force-push or rewrite published history
- does not modify `.git/` internals

Read the skill before running it in a sensitive repository.

## Installation

Inside Claude Code:

```text
/plugin marketplace add Srikanth-Mohankumar/claude-setup-auditor
/plugin install claude-setup-auditor@srikanth-claude-tools
```

Then reload plugins if your Claude Code version asks you to.

## Usage

Audit the current repository plus your user-level Claude configuration:

```text
/claude-setup-auditor:audit-setup
```

Scope the audit to a path:

```text
/claude-setup-auditor:audit-setup ./backend
```

Depending on your Claude Code version/UI, the installed skill may also appear in the slash-command picker as `audit-setup`.

## What it does

The workflow has five phases:

1. **Ground truth** — reads current Claude Code docs instead of relying on model memory.
2. **Inventory** — finds all relevant Claude configuration and measures always-loaded context.
3. **Bootstrap and repair** — creates missing essentials and fixes stale, duplicated, vague, or misplaced configuration.
4. **Verify** — validates JSON/frontmatter, runs documented commands, and re-measures context.
5. **Record** — appends a dated audit report to `docs/claude-setup-audit.md`.

## Philosophy

**Fewer, sharper files.**

If Claude can learn something by reading the code, it usually should not consume every session's context.

Conditional guidance belongs in on-demand skills. Deterministic policy belongs in hooks. Unused integrations should not stay enabled just because they were useful once.

A confidently wrong instruction file is worse than no instruction file.

## Requirements

- Claude Code with plugin/skill support
- Git recommended for the safest workflow
- Network access so the audit can verify current Claude Code documentation

If official documentation cannot be fetched, the audit stops rather than "upgrading" your setup from potentially stale model knowledge.

## Review before running

This is not a read-only linter. It can modify Claude configuration in the selected repository and under `~/.claude/`.

The workflow creates backups/branches before edits, but you should still review the skill source before using it in production or security-sensitive environments.

## Versioning

This project follows semantic versioning.

Current release: **1.0.0**

## License

MIT

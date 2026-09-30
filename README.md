# Claude Setup Auditor

Keep your Claude Code setup lean, current, and useful.

`claude-setup-auditor` is a public Claude Code plugin that reviews project and user-level Claude configuration against current Claude Code documentation, identifies stale or duplicated setup, and recommends concrete ways to reduce always-loaded context and improve skill/agent quality.

## Why this exists

Claude Code setups tend to accumulate over time:

- oversized or stale `CLAUDE.md` files
- duplicated rules
- skills that no longer trigger reliably
- subagents with unclear responsibilities or overly broad scope
- policy text that would be more reliable as hooks
- unused MCP servers and plugins consuming context
- missing or unclear verification commands

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
- relevant `~/.claude/` configuration
- hooks
- MCP servers
- plugins
- always-loaded vs on-demand context

## Installation

Inside Claude Code:

```text
/plugin marketplace add Srikanth-Mohankumar/claude-setup-auditor
/plugin install claude-setup-auditor@srikanth-claude-tools
```

## Usage

Audit the current setup:

```text
/claude-setup-auditor:audit-setup
```

Scope the audit to a path:

```text
/claude-setup-auditor:audit-setup ./backend
```

Depending on your Claude Code version/UI, the installed skill may also appear in the slash-command picker as `audit-setup`.

## What you get

The skill:

1. checks current Claude Code documentation instead of relying only on model memory
2. inventories Claude-related configuration
3. identifies stale, duplicated, misplaced, or overly permanent instructions
4. reviews skill triggering and agent responsibilities
5. flags hook, MCP, plugin, and context-overhead opportunities
6. returns prioritized recommendations with concrete file-level changes

The public plugin is intentionally **read-only**: it recommends changes rather than silently rewriting a developer's repository or user-level configuration.

## Philosophy

**Fewer, sharper files.**

If Claude can learn something by reading the code, it usually should not consume every session's context.

Conditional guidance belongs in on-demand skills. Deterministic policy often belongs in hooks. Unused integrations should not remain enabled solely because they were useful once.

A confidently wrong instruction file is worse than no instruction file.

## Requirements

- Claude Code with plugin/skill support
- network access so the skill can verify current Claude Code documentation

## Versioning

This project follows semantic versioning.

Current release: **1.0.0**

## License

MIT

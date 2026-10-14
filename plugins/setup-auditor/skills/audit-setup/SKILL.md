---
name: audit-setup
description: Reviews a Claude Code setup and recommends improvements. Use when the user wants to inspect, modernize, verify, or reduce context overhead in CLAUDE.md, skills, agents, rules, hooks, settings, MCP servers, plugins, commands, or ~/.claude configuration.
argument-hint: "[optional path, e.g. ./backend]"
allowed-tools: [Read, Glob, Grep, WebFetch]
version: 1.0.0
---

# Claude setup audit

Review the requested Claude Code setup and produce a concrete improvement plan without editing files.

Scope: $ARGUMENTS. If empty, inspect the current repository and relevant Claude configuration that is available to read.

## 1. Verify current conventions

Use current Claude Code documentation rather than relying on model memory. Review the latest guidance for memory files, skills, subagents, settings, hooks, the `.claude` directory, configuration debugging, and context usage.

If current documentation cannot be retrieved, clearly state that limitation before making recommendations about structure or conventions.

## 2. Inventory the setup

Inspect relevant configuration, including:

- root and nested `CLAUDE.md`
- `CLAUDE.local.md`
- `AGENTS.md`
- `.claude/rules/`
- `.claude/skills/`
- `.claude/agents/`
- `.claude/commands/`
- `.claude/settings.json`
- `.claude/settings.local.json`
- `.mcp.json`
- configured hooks
- plugin configuration

Identify what appears to load every session versus what loads on demand. Estimate the size of always-loaded instruction context when possible.

## 3. Review quality

Check for:

- stale or unverifiable instructions
- duplicated or contradictory guidance
- generic advice Claude can infer from code
- directory-specific guidance placed too globally
- conditional guidance that would fit better in an on-demand skill
- skill descriptions that are unlikely to trigger reliably
- overlapping skills
- subagents with unclear responsibilities
- policies that would be more reliable as hooks
- unused integrations that add persistent context
- missing or unclear verification commands

## 4. Recommend improvements

Order recommendations by impact. For every recommendation, include:

- the file or configuration area affected
- what is wrong or inefficient
- the proposed change
- why it improves quality, reliability, or context usage
- any risk or tradeoff

Do not recommend deleting or disabling something solely to reduce file count. Each recommendation must be justified by evidence from the repository or current Claude Code documentation.

## 5. Report

Return a concise audit containing:

1. overall setup health
2. highest-impact findings
3. always-loaded context observations
4. skills and agents that need attention
5. settings, hooks, MCP, or plugin findings
6. prioritized recommended changes
7. items that should remain unchanged

For every skill or agent description you recommend changing, include an example user prompt that the improved description should match.

## Guiding principle

Prefer fewer, sharper, verified instructions over a large configuration that is stale, duplicated, speculative, or permanently loaded without clear value.

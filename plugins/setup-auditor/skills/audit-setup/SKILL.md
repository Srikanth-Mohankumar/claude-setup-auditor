---
name: audit-setup
description: Audits a Claude Code setup read-only — measures how many tokens CLAUDE.md, rules, skills and agents load into every session, finds stale, duplicated, broken or badly-triggering configuration, and returns a scored, prioritized fix list. Use when the user asks to review, audit, clean up, slim down or modernize their Claude setup, CLAUDE.md, skills, agents, hooks, settings or MCP servers, or asks why a skill is not triggering or where their context is going.
argument-hint: "[path to project, default: current directory]"
allowed-tools: Read Glob Grep WebFetch Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/scan.py *)
metadata:
  version: 2.0.0
---

# Claude setup audit

Audit the Claude Code setup for the project at `$ARGUMENTS` (empty means the current directory)
plus the user's `~/.claude/` configuration. **Read-only: never edit, create or delete a file in
this skill.** Fixing is a separate, explicitly invoked skill.

## 1. Measure first

Run the deterministic scanner and keep its output — it is the factual backbone of the report:

```
python3 ${CLAUDE_SKILL_DIR}/scripts/scan.py <project path>
```

It reports always-loaded vs on-demand context per file, a mechanical health score, and findings
with IDs (CSA001–CSA018) for broken imports, invalid JSON, dead path references, duplicated rules,
rules whose values disagree between copies, vague or oversized skill descriptions, missing hook
scripts, blanket permissions and plain-text secrets. Do not re-derive what it already measured, and do not contradict its numbers. If a
finding is a false positive after reading the file, say so and why.

Other agents' instruction files (AGENTS.md, GEMINI.md, Cursor, Copilot and Windsurf rules) are
compared for conflicting values automatically. If the user keeps other copies of their rules (a
backup, a docs page, mirrored skill folders), pass each with `--mirror <path>`.

Never print a secret the scanner flags; refer to it by file and line only.

## 2. Verify conventions against current docs

The scanner encodes mechanical rules; judgment calls need current docs, not memory. Fetch
`https://code.claude.com/docs/en/claude_code_docs_map.md` and read the pages relevant to what
this setup actually uses — usually `memory`, `skills`, `sub-agents`, `hooks`, `settings`,
`best-practices` and `features-overview`. If the fetch fails, say so at the top of the report and
mark convention-based recommendations as unverified.

## 3. Review what a script cannot judge

Read the always-loaded files and every skill/agent the scanner listed, then apply
[references/checklist.md](references/checklist.md). The questions that matter most:

- **Earns its place?** Is each always-loaded line something Claude could not learn by reading the
  code, and does it apply to most sessions? If not: delete, move to a nested `CLAUDE.md`, a
  `paths:`-scoped rule, or a skill.
- **True?** Spot-check factual claims — commands, paths, versions, framework names — against the
  repo. A confidently wrong instruction is worse than none.
- **Triggers?** For each skill and agent, write the prompt a user would actually type and judge
  whether the description would match it. Look for overlapping descriptions that compete.
- **Policy or plea?** A rule that must never be broken (protected paths, formatting, secrets)
  belongs in a hook, not prose.
- **Verifiable?** Are the real test/lint/build commands documented? This is usually the single
  highest-value line in a CLAUDE.md.

## 4. Report

Use exactly this structure so repeated runs compare cleanly:

```
## Setup health: <score>/100 · ~<N> tokens always loaded
<two sentences: overall state and the single most valuable change>

### Top fixes
| # | Impact | File | Problem | Change |
(at most 7 rows, highest impact first; each row concrete enough to apply without re-reading)

### Context budget
<largest always-loaded items, what could move on-demand, estimated tokens saved — label as estimate>

### Skills and agents
<per item needing work: problem, proposed description, and an example prompt it should match>

### Settings, hooks, MCP and plugins
### Keep as is
<what is already good, so nobody "fixes" it>

Next step: run /setup-auditor:fix-setup to apply these on a reviewable branch.
```

Rules for the report:

- Every recommendation cites evidence: a scanner finding ID, a file and line, or a docs page.
- Never recommend removing something only to shrink a number; say what is lost.
- Token savings are estimates from the scanner's chars/4 method; say so.
- If the setup is already good, say so in two lines. Do not invent work.

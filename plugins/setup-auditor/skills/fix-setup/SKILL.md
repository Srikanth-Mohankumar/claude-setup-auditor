---
name: fix-setup
description: Applies Claude setup audit fixes on a dedicated git branch with a backup of every user-level file, one commit per change area, and a before/after context measurement. Run explicitly after audit-setup.
argument-hint: "[path to project, default: current directory]"
disable-model-invocation: true
allowed-tools: Read Glob Grep WebFetch Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/audit-setup/scripts/scan.py *)
metadata:
  version: 2.0.0
---

# Fix the Claude setup

Apply the improvements an audit identifies for the project at `$ARGUMENTS` (empty means the
current directory) and the user's `~/.claude/`. Every change must be reviewable and trivially
reversible. Edits still go through the user's normal permission prompts.

## 0. Safety setup — before touching anything

1. Run `git status`. If the project is not a git repository, stop and ask the user how they want
   changes protected; do not `git init` on their behalf.
2. If the tree is dirty, stop and ask the user to commit or stash first. Never stash or discard
   their work yourself.
3. Create and switch to branch `setup-audit/<YYYY-MM-DD>`. All project changes happen there.
4. User-level files under `~/.claude/` affect every project and are not in this repo's git.
   Apply project changes first. Then list proposed user-level edits and ask the user to confirm
   them. Before editing any confirmed file, copy it to
   `~/.claude/.audit-backup/<YYYYMMDD-HHMMSS>/<same relative path>`. No confirmation or no backup
   means no edit. If you cannot ask, for example in a non-interactive run, leave them as proposals.

Never, in any phase: write a secret, token or credential into a file; delete an untracked file
without a backup; touch `.git/` internals; run `sudo`; push, force-push or rewrite history;
weaken an existing deny rule or security hook.

## 1. Baseline

Run the scanner and keep its output as the baseline:

```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/audit-setup/scripts/scan.py <project path>
```

If an audit report already exists in this conversation, use its recommendations. Otherwise
follow steps 2–3 of [the audit skill](../audit-setup/SKILL.md) and its
[checklist](../audit-setup/references/checklist.md) to decide what to change. Fetch the current
Claude Code docs before changing any convention; if they cannot be fetched, stop.

## 2. Apply, one area per commit

Work in impact order. Commit after each area with a message naming what changed and why:

1. **Broken things** — invalid JSON, broken `@imports`, missing hook scripts, frontmatter errors,
   dead path references.
2. **Always-loaded context** — cut what Claude can infer from code; move directory-specific
   guidance to nested `CLAUDE.md` or `paths:` rules; move long conditional procedures into skills;
   remove duplicates, keeping the copy in the right scope.
3. **Verification commands** — find the real test/lint/typecheck/build commands, run each once,
   and document only those that succeeded. Do not remove an already documented command that
   matches the project's scripts just because it fails for environmental reasons (dependencies
   not installed, service not running); report it instead.
4. **Skills and agents** — rewrite descriptions that will not trigger (what it does + when, in
   the user's words); add `disable-model-invocation: true` to side-effecting skills the user always
   runs by hand; narrow agent tools.
5. **Settings and hooks** — replace blanket allows with targeted rules; turn never-break prose
   rules into hooks; gitignore personal config.

For confirmed user-level edits (not in git), list each one with its backup path instead of a commit.

Do not delete a skill, agent, MCP server or plugin the user may rely on without asking. Do not
invent conventions you could not verify in docs or the repo; leave them out.

## 3. Verify

- Re-run the scanner. No new findings may appear; fix any that did.
- Every JSON file you touched parses; every skill and agent you touched has valid frontmatter.
- Every command you documented ran successfully in this session.

## 4. Report

Keep it to one screen:

```
## Setup fixed: <old score> → <new score> · ~<old> → ~<new> tokens always loaded
Branch: setup-audit/<date> (<n> commits) · Backups: <path or "none needed">

| Commit | What changed | Why |
...

Not changed: <recommendations skipped and why>
Review with: git diff <base>...setup-audit/<date>
Undo with: git switch <base> && git branch -D setup-audit/<date>
```

Token figures are estimates (chars/4); say so once.

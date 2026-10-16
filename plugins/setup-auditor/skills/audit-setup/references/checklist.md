# Review checklist

Judgment calls the scanner cannot make. Each item names the docs page that backs it; re-check
that page before relying on the rule, because conventions change.

## Always-loaded instructions (CLAUDE.md, rules without `paths:`, auto memory)

Docs: `memory`, `best-practices`, `features-overview`

- Content Claude can infer from the code — directory listings, language name, "uses React",
  restated linter config — costs every session and adds nothing. Cut it.
- Guidance for one directory or file type belongs in that directory's `CLAUDE.md` (loads on
  demand) or in a `.claude/rules/*.md` file with `paths:` frontmatter.
- Long conditional procedures ("when doing a migration…") belong in a skill: only its name and
  description cost context until it is used.
- `@imports` do not save context; imported files load at launch like the importer.
- `AGENTS.md` is read only when no `CLAUDE.md` exists in the tree. With both present, either
  import it (`@AGENTS.md`) or accept that Claude ignores it.
- Contradictions between scopes: more specific scope wins, but the model still sees both. Remove
  the losing copy.
- Copies drift. When the same rules live in several places (CLAUDE.md and AGENTS.md, a backup,
  mirrored skill folders), pick one source and rebuild the others from it. CSA018 flags copies whose
  wording matches but whose numbers or `values` differ; it cannot tell which copy is right.
- Instructions must be checkable. "Be careful with the database" → "Never run migrations against
  `prod`; use `make migrate-dev`."
- Verification commands (test, lint, typecheck, build) should be present and runnable.

## Skills

Docs: `skills`

- The description is the trigger. It should say what the skill does **and** when to use it, in
  the words a user types, with the use case first (description + `when_to_use` are cut at 1,536
  characters in the listing).
- Two skills whose descriptions would both match the same prompt will compete; merge or sharpen.
- A skill the user always invokes by hand, especially one with side effects, should set
  `disable-model-invocation: true` — it then costs no listing context and never fires by surprise.
- Keep `SKILL.md` under ~500 lines; move reference detail into files the skill links to.
- `allowed-tools` pre-approves tools; it does not restrict others. Scope Bash rules narrowly.
- Unknown frontmatter fields are silently ignored — e.g. `version` belongs under `metadata:`.

## Subagents

Docs: `sub-agents`

- One responsibility per agent; the description says concretely when to delegate.
- Tools limited to what the job needs. Model chosen on purpose.
- The prompt says what the agent must return; vague hand-backs waste the round trip.
- Agent descriptions load every session; Claude Code warns above ~15,000 combined tokens.

## Hooks

Docs: `hooks`

- A rule in prose that must never be broken (protected paths, generated files, formatting,
  secret files) is more reliable as a `PreToolUse`/`PostToolUse` hook.
- Hook scripts must exist, be executable, and fail closed where safety depends on them.
- Hooks run with the user's permissions; review what each command does.

## Settings and permissions

Docs: `settings`, `permissions`

- Precedence: managed > command line > `.claude/settings.local.json` > `.claude/settings.json` >
  `~/.claude/settings.json`.
- Allow rules should be targeted (`Bash(npm test *)`), not blanket (`Bash`).
- Deny reads of `.env`, credentials and key files.
- `.claude/settings.local.json` and `CLAUDE.local.md` are personal and should be gitignored.

## MCP servers and plugins

Docs: `mcp`, `plugins`

- Servers live in `.mcp.json` (project, shared) or `~/.claude.json` (user and local scopes).
- Tool search defers MCP tool schemas by default, but each server still starts, runs and can be
  called. Remove servers nothing uses.
- Credentials belong in environment variables (`${VAR}`), never literal in `.mcp.json`.
- Plugins add skills, agents and hooks; review what an enabled plugin brings in.

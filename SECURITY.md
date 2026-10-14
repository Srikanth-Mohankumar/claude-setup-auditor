# Security

## Reporting a security issue

Please do not publish secrets, credentials, private repository content, or other sensitive data in a public issue.

For general bugs, open a GitHub issue with a minimal reproducible example that contains no confidential information.

## Scope

- `audit-setup` and `scan.py` are read-only. They do not edit repository or user-level files and make no network calls apart from fetching Claude Code documentation. The scanner reports suspected secrets by file and line, never by value.
- `fix-setup` edits files only when you invoke it explicitly. It works on a dedicated git branch, does not run on a dirty tree, never pushes or rewrites history, and asks before changing user-level `~/.claude` files, backing each one up first.

As with any developer tool, avoid sharing confidential configuration or credentials in public bug reports.

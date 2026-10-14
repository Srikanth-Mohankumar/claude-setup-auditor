# Contributing

Contributions are welcome.

Please keep changes focused on making Claude Code configuration safer, smaller, more accurate, and easier to maintain.

Before submitting a change:

1. Confirm the behavior against current Claude Code documentation.
2. Avoid adding permanent context that Claude can discover from the repository.
3. Keep autonomous edits recoverable.
4. Do not weaken secret, destructive-command, or history-rewrite protections.
5. Add a scanner check only with a test that plants the problem and fails without the check.
6. Run `python3 -m unittest discover tests` and `claude plugin validate .`.
7. Update `CHANGELOG.md` when behavior changes.

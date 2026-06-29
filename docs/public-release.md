# Public Release Hygiene

Use this checklist before pushing this repository to a public GitHub remote.

## Tracked Files

- Keep local databases, logs, generated state, and machine-specific settings out
  of Git. Use environment variables or ignored `.local` files for local state.
- Keep clonable Codex assets under `.codex/agents/` and
  `.codex/skills/codex-kanban/`.
- Run a tracked-file scan before release for absolute user paths, credentials,
  local databases, generated state, and private infrastructure names.

## Git Refs

Push only the intended release branch or tag:

```bash
git push origin release/0.1.1
```

Do not use `git push --mirror` or `git push --all` from a working repository
that may contain development-only refs. If a clean public export is needed,
clone only the intended branch into a fresh directory and push from that clone.

## Git Identity

Commit author metadata and signed-commit identities are part of Git history.
If a public release must not expose personal author names, email addresses, or
signing-key identity, rewrite history only after choosing the intended public
author/signing identity and getting explicit approval for the destructive
rewrite.

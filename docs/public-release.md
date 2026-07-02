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

Before pushing refs or tags, record the release scope on the Kanban release
card: included/excluded cards and branches, affected apps/repos/worktrees, and
deployment dispositions for anything production-facing.

Push only the intended release branch or tag, then fast-forward `main` to the
same commit SHA after release-branch CI passes:

```bash
git push origin refs/heads/release/0.1.3:refs/heads/release/0.1.3
git push origin refs/heads/release/0.1.3:refs/heads/main
git push origin refs/tags/v0.1.3:refs/tags/v0.1.3
```

Do not use `git push --mirror` or `git push --all` from a working repository
that may contain development-only refs. If a clean public export is needed,
clone only the intended branch into a fresh directory and push from that clone.

The repository protects `main` with the `test` status check. Because full CI
runs on `release/**` and not on `main` pushes, `main` should accept only a
commit SHA that already passed release-branch CI. A merge commit, squash commit,
or rebased main-only SHA will not have the release-branch check attached and
should be rejected.

## Git Identity

Commit author metadata and signed-commit identities are part of Git history.
If a public release must not expose personal author names, email addresses, or
signing-key identity, rewrite history only after choosing the intended public
author/signing identity and getting explicit approval for the destructive
rewrite.

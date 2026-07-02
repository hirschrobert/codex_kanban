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

Push only explicit release refs, the approved `main` release-merge
fast-forward ref, and release tags. Feature, fix, and release metadata commits
stay on `release/<version>`. After release-branch CI passes on the release tip,
create a visible no-fast-forward release merge commit from the current public
`main` and the release branch, then run CI on that exact merge commit before
`main` moves:

```bash
version=0.1.6
release_branch="release/${version}"

git push origin "refs/heads/${release_branch}:refs/heads/${release_branch}"
# Wait for CI to pass on the release branch tip.

git fetch origin main "${release_branch}"
git switch --detach origin/main
git merge --no-ff --no-edit "origin/${release_branch}"
merge_sha="$(git rev-parse HEAD)"

git branch -f "${release_branch}" "${merge_sha}"
git push origin "${merge_sha}:refs/heads/${release_branch}"
# Wait for CI to pass on release/<version> at ${merge_sha}.

git push origin "${merge_sha}:refs/heads/main"
git tag -a "v${version}" "${merge_sha}" -m "Release ${version}"
git push origin "refs/tags/v${version}:refs/tags/v${version}"
git branch -f main "${merge_sha}"
git switch main
```

Do not use `git push --mirror` or `git push --all` from a working repository
that may contain development-only refs. If a clean public export is needed,
clone only the intended branch into a fresh directory and push from that clone.

The repository protects `main` with the `test` status check. Because full CI
runs on `release/**` and not on `main` pushes, `main` should accept only the
release merge commit SHA that already passed release-branch CI. A squash
commit, rebased commit, rewritten commit, or other main-only SHA will not have
the release-branch check attached and should be rejected.

The release merge commit gives developers a clear first-parent marker on
`main`, while the second parent keeps the feature/fix/release metadata commits
visibly grouped on the release branch. Do not rewrite already-published history
to retrofit this shape; apply it to future releases.

## Git Identity

Commit author metadata and signed-commit identities are part of Git history.
If a public release must not expose personal author names, email addresses, or
signing-key identity, rewrite history only after choosing the intended public
author/signing identity and getting explicit approval for the destructive
rewrite.

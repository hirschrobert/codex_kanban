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
fast-forward ref, and release tags. Feature and fix work starts on
card-specific branches and merges into `release/<version>` only after human
final review; release metadata commits stay on `release/<version>`. After each
approved branch lands, refresh the remaining active feature/fix branches from
the updated release branch. Create the visible no-fast-forward release merge
commit locally before the first public push for that release, then push that
merge commit to the release branch once. CI should run once on the exact merge
SHA that will later fast-forward `main`:

```bash
version=0.1.7
release_branch="release/${version}"

git fetch origin main
git switch --detach origin/main
git merge --no-ff -m "Merge ${release_branch} into main" "${release_branch}"
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

For a public repository, no `gh` dependency is required to wait for the
release-branch CI gate. You can use the GitHub Actions page, or poll the REST
API with `curl` and Python's standard library:

```bash
repo="hirschrobert/codex_kanban"

while :; do
  read -r status conclusion url < <(
    curl -fsS -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/${repo}/actions/runs?branch=${release_branch}&head_sha=${merge_sha}&event=push&per_page=1" \
      | python3 -c 'import json, sys
data = json.load(sys.stdin)
runs = data.get("workflow_runs") or []
run = runs[0] if runs else {}
print(run.get("status", "missing"), run.get("conclusion") or "pending", run.get("html_url", ""))'
  )
  printf 'CI status: %s %s %s\n' "${status}" "${conclusion}" "${url}"
  case "${status}:${conclusion}" in
    completed:success) break ;;
    completed:*) exit 1 ;;
  esac
  sleep 10
done
```

For a private repository, add an `Authorization: Bearer ${GITHUB_TOKEN}` header
to the `curl` command.

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

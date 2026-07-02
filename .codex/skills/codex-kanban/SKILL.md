---
name: codex-kanban
description: Coordinate project work through the local Codex Kanban dashboard with auditable cards, visible status, board-scoped agents, and release/deploy handoffs.
---

# Codex Kanban

Use Codex Kanban as the shared coordination surface for humans, the main AI
agent, and optional subagents. Keep the dashboard generic: project-specific
domain, release, deployment, security, and verification rules stay in the
current repo's `AGENTS.md` and registered instruction files.

For command details and longer examples, see `docs/codex-kanban.md`.

## When To Use It

- Use Kanban for concrete feature, fix, docs, test, review, release,
  project-registration, or multi-agent work that changes files, plans work,
  hands work between agents, or affects project state.
- Skip Kanban for trivial local checks, simple command output, or discussion
  that does not change project work.
- Keep exploratory design light and read-only until the human approves
  implementation.

## First Move

1. Read the current repo `AGENTS.md`, then nearest nested `AGENTS.md`.
2. Find or register the project board. First use registered projects/current
   cwd matching; ecosystems match any registered app, repo, or worktree path.
   Prefer `${CODEX_KANBAN_URL:-http://127.0.0.1:8766}`; direct SQLite fallback
   is OK.
3. Refresh board-scoped AI agents from current generic defaults and
   discoverable project-local profiles. The startup overview command below does
   this and updates the dashboard people/assignee lists.
4. Inspect a lean non-archived card overview before work. Human-added cards
   are authoritative unless the user redirects the task. Remember archived
   cards may exist and may need a separate archived search for older context.
5. Select the relevant card or create one if none fits.
6. Record start, block, handoff, finish, and delegated feedback through the
   ingester, CLI, or HTTP API.

## Intake

Human requests should become durable cards with enough context for another
agent to continue without the chat transcript.

Split multi-intent requests before implementation starts. If one human message
contains independent features, fixes, apps, repos, user roles, UI flows, or
deployment scopes, create separate task cards. Use a parent coordination card
plus child cards when the work shares one release or branch context; otherwise
use sibling cards. Do not make one implementation card whose title or
description bundles unrelated deliverables.

Prefer these metadata fields when known:

- `intake_kind`: `feature_request`, `error_report`, `coordination`,
  `maintenance`, `review`, or `release`;
- `intake_source`: usually `main_agent`, `dashboard`, `cli`, or `automation`;
- `reported_by`, `impact`, `evidence`, and `affected_paths`;
- for ecosystems, every affected app, repo, worktree, or file path.

For non-trivial card descriptions, use one clean rationale block:

- a short request/problem summary;
- `Why this card exists:`;
- `If this is not fixed:`;
- `Acceptance criteria:`.

Do not duplicate those headings. If later information is feedback or readiness
context, add a card comment. If it is separate work, create a child card or a
new sibling card before assigning implementation.

## Useful CLI Shapes

Use the project CLI when possible. `PYTHONPATH` must point at the
`codex_kanban` checkout that contains `kanban_server`, not necessarily the
project being inspected. Set `CODEX_KANBAN_REPO` when working from another
repo; from this checkout, the Git root fallback is enough:

```bash
KANBAN_REPO="${CODEX_KANBAN_REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
test -d "$KANBAN_REPO/kanban_server" || {
  echo "Set CODEX_KANBAN_REPO to the codex_kanban checkout"
  exit 1
}
```

```bash
PYTHONPATH="$KANBAN_REPO" python3 -m kanban_server.project overview \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --cwd "$PWD" \
  --repo "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" \
  --done-limit 5 \
  --register-if-missing
```

Use full `snapshot` only when you need events, participants, comments, or
archived-inclusive board state. Use `--done-limit -1` only when completed-card
history is needed; first overview should keep done-card history short. If the
human asks to reload the `codex-kanban` skill, rerun the overview command so
current generic/default and project-local agents are synced into the UI.

```bash
PYTHONPATH="$KANBAN_REPO" python3 -m kanban_server.project card-create \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --board <board> \
  --title "<short title>" \
  --description "<request summary>" \
  --why "<reason>" \
  --risk "<what breaks if skipped>" \
  --acceptance "<observable done condition>" \
  --affected-path <repo-or-app-path> \
  --assignee <board-scoped-participant-id>
```

```bash
PYTHONPATH="$KANBAN_REPO" python3 -m kanban_server.project card-move <numeric-card-id> \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --status in_progress \
  --target-repo <repo-path> \
  --target-branch <upcoming-release-branch> \
  --start-sha <target-sha-before-work> \
  --handoff-sha <target-sha-after-work> \
  --deployment-disposition "<label>|<repo-or-app-path>=<status>:<note>" \
  --check "<command or verification>"
```

Use `--clear-blocker` to remove a resolved blocker. If an assignee is missing,
register it first with `participant-upsert`; do not invent participant IDs.

Agent event ingestion:

```bash
PYTHONPATH="$KANBAN_REPO" python3 -m kanban_server.ingest \
  --board <board> \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --event-type agent.started \
  --participant-id <board-agent-id> \
  --display-name <agent-name> \
  --participant-kind agent \
  --status running \
  --current-card-external-id <CARD-ID> \
  --current-scope "<repo/path or task scope>"
```

`agent.finished`, `agent.feedback`, `agent.handoff`, `subagent.stopped`,
`subagent.feedback`, and `subagent.handoff` events with a card and message are
mirrored into card comments so the owner can act on them.

## Project Registration

Register one repo with one root. Register ecosystems with repeated `--path` and
`--instruction` values so hooks and agents can map directories to the right
board and instructions.

Use board-scoped participants only:

- `<board>-ai-agent-manager`
- `<board>-kanban-auditor`
- `<board>-project-architect`
- `<board>-project-implementer`
- `<board>-project-reviewer`
- `<board>-project-release-manager`
- other registered project-local profiles.

Do not assign cards, events, comments, or participant state across boards. If a
board-scope error appears, fix the board/card/participant ID instead of
bypassing Kanban.

## Multi-Agent Work

Codex Kanban is a standing project instruction to consider specialized
subagents for concrete work when delegation can improve software quality,
usability, safety, maintainability, or data integrity. Choose from all available
board-scoped profiles, including project-local profiles, but do not spawn every
profile by default; select the smallest relevant set for independent
implementation, review, release-readiness, documentation, audit, domain,
contract, architecture, or test-strategy scopes. The main agent stays
responsible for routing, integration, card hygiene, and final user summary.

Some Codex environments may still disallow spawning from standing repo or skill
instructions alone. If delegation is useful but the tool is unavailable or
disallowed, create/update the coordination cards and surface the blocker
instead of silently doing delegated work in the parent context.

Before delegating:

- create/update the parent coordination card;
- create one child card for the main implementer and each delegated subagent
  doing material work;
- assign each child to a board-scoped participant;
- choose disjoint write scopes; read-only reviewers/auditors may run in
  parallel;
- record target repo, target branch, starting SHA, worktree path, checks, and
  acceptance criteria.

Avoid overlapping implementation cards. Treat these as conflict signals:

- same target repo and target branch;
- same feature branch;
- same worktree path;
- same declared files;
- missing target branch on active implementation work.

Active unfinished work should target the upcoming unreleased release branch. If
none exists, create one instead of targeting `main` or `master`.

## Release And Deploy

For release, deploy, or "merge to main" work, scope is all completed,
approved, or requested work ahead of the maintained integration branch unless
the human/project instructions explicitly exclude it. Do not include only the
card currently in focus.

Before preparing, merging, tagging, publishing, or deploying:

- enumerate every registered repo/app/worktree in scope;
- enumerate ready, in-progress, review, blocked, and done cards targeting the
  release branch, repo, app, worktree, or an ahead branch;
- enumerate release/prerelease/task branches ahead of the integration branch;
- give each card, branch, and affected app exactly one disposition: included,
  deployed, not required, excluded with reason, or blocked with blocker;
- record dispositions with `affected_paths` and `deployment_dispositions`;
- stop if a done/approved card, ahead branch, or affected app has no
  include/exclude/deploy disposition.

Release work should start a read-only `project_release_manager` or
`kanban_auditor` for the intake audit whenever subagents are available and the
task is more than a trivial status check.

## Card Contract

Cards should accumulate only the fields needed for handoff:

- board/card ID, title, status, owner/assignee, priority, parent/child links;
- target repo/branch, start SHA, handoff SHA, feature branch, worktree path;
- affected paths, affected registered project paths, deployment dispositions;
- files changed, checks run, failures, assumptions, blockers;
- comments for human/agent feedback and follow-up child cards for separate
  work.

A parent depends on its children and cannot advance into active/review/done
until child dependencies are done.

Recurring cards may use `daily`, `weekly`, or `monthly` with a repeat time, but
must have a target branch and belong to an active registered project board.

## Approval Boundaries

Kanban state is never approval for risky actions. Follow the current repo's
`AGENTS.md` and ask the human before production changes, destructive actions,
migrations, service restarts, package publishing, release tags, credentials,
signing, or other project-specific approval gates.

Public release rules that must remain explicit:

- update `CHANGELOG.md` and AI-assistance disclosure when the project requires
  it;
- audit tracked files and intended push refs for personal data, local paths,
  local databases, secrets, and generated coordination state;
- push only explicit release branches, the approved `main` release-merge
  fast-forward ref, or release tags; never `--mirror` or `--all` from a
  development repo;
- keep feature, fix, and release metadata commits on `release/<version>`;
- integrate a release with an explicit no-fast-forward merge commit whose first
  parent is the previous `main` and whose second parent is the release branch
  tip;
- create that merge commit before the first public push for the release, then
  push it to `release/<version>` once and wait for CI on that exact SHA before
  advancing `main`;
- advance `main` only by fast-forwarding it to the exact release merge commit
  SHA that passed release-branch CI; never squash, rebase, rewrite, or create
  an untested main-only commit.

## Final Response

Summarize card IDs touched, agents used, changed files, checks, failures, and
follow-up cards. If Kanban updates were impossible, say why and include the
intended status update.

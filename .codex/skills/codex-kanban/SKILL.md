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
4. Inspect a lean non-archived card overview before work. Its default first
   peek keeps active cards and done cards updated within the last two days;
   deliberately request older done or archived history only when the task needs
   it. Human-added cards are authoritative unless the user redirects the task.
5. Select the relevant card or create one if none fits. For implementation
   work, confirm the card has a target release branch and an appropriate
   feature/fix branch before editing files. Prefer reusing an unmerged branch
   when the new local request is a same-object/same-topic follow-up on that
   branch; create a new branch when the work is unrelated or independently
   reviewable.
6. Let the main agent decide whether delegation helps and which available
   built-in, custom, or board-scoped agents best fit. Board profiles are offers,
   not a requirement, and skipping delegation needs no Kanban justification.
7. Record start, block, handoff, finish, and delegated feedback through the
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

Do not duplicate those headings. If later information is feedback, findings,
decisions, blockers, readiness context, or a finished contributor summary, add
a card comment. If it is separate work, create a child card or a new sibling
card before assigning implementation.

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
archived-inclusive board state. Both default snapshot and overview omit done
cards older than two days. Use `--done-limit -1` only when complete done-card
history is needed; search archived cards separately. If the
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

```bash
PYTHONPATH="$KANBAN_REPO" python3 -m kanban_server.project card-comment <numeric-card-id> \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --board <board> \
  --participant-id <board-agent-id> \
  --body "<durable note, finding, blocker, or contributor result>"
```

Use `card-comment` for durable context that future work should read but that is
not a new task by itself. For delegated work, comment on the parent coordination
card with the subagent's result, findings, decisions, blockers, and next steps.
Also update the child card status/checks/handoff fields for execution state.

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

Linked Git worktrees belong to the project registered for their primary
repository (the worktree reported by Git's common directory), not to separate
projects or boards. Keep every card, participant, and event on that origin
board. Record the primary checkout in `target_repo` and the checkout that
actually contains the changes in `worktree_path`; the dashboard exposes the
worktree as the card's change source without treating it as another project.

Use board-scoped participants for Kanban state:

- `<board>-ai-agent-manager`
- `<board>-codex-subagents` for native built-in or unregistered runtime types
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

Codex Kanban coordinates work that Codex chooses to delegate; it does not force
delegation or select agents on behalf of the main agent. The main agent decides
whether the task benefits from subagents and whether Codex built-ins, arbitrary
custom agents, registered board profiles, or single-agent execution are the
best fit. Registered board profiles are an optional catalog of project-aware
specialists, not the exclusive agent pool. The main agent stays responsible for
routing, integration, card hygiene, and the final user summary.

Agent profiles omit `model`, so inheritance from the calling session is the
safe default. Before each delegation, the main agent should deliberately choose
the model strategy when the current Codex surface supports per-agent model
selection:

- inherit the current model for ambiguous implementation, architecture,
  release, security, data-integrity, or high-risk review work;
- request a supported lighter model for bounded, low-risk scans, triage,
  summarization, or high-parallelism exploration when speed/cost is preferable;
- fall back to inheritance when the spawn surface cannot select a model;
- never infer the model from the role profile: record and display the actual
  runtime model reported by Codex hooks.

Keep model choice separate from role identity so concurrent instantiations of
one role may use different models without creating duplicate People entries.

People liveness observes every Codex-spawned subagent. Exact registered profile
types use their durable board role; built-in `default`, `worker`, `explorer`,
and unregistered custom types use `<board>-codex-subagents`, with the actual
reported type shown on each runtime instance.

When the main agent deliberately chooses a registered Kanban profile:

- select the exact Codex custom-agent type whose `name` matches the assigned
  board profile, such as `project_reviewer`; a Kanban assignment, role name in
  the prompt, or `task_name` does not select that agent or load its TOML file;
- treat `task_name` only as the concrete task/thread label, not as the agent
  type. Use the spawn surface's agent-type/profile selector and verify the
  returned runtime or `SubagentStart` event reports the requested type;
- never present a `default` agent as a named specialist. If exact profile
  selection is unavailable, either let the main agent choose a suitable native
  agent shown under `<board>-codex-subagents`, or surface the limitation when
  the requested specialist configuration is essential.

For delegated work that needs durable independent tracking:

- create/update the parent coordination card;
- create child cards for contributors whose scope needs its own branch,
  worktree, checks, blocker, or handoff; do not require cards for ephemeral
  exploration or support agents;
- assign tracked children to the matching board-scoped participant;
- choose disjoint write scopes; read-only reviewers/auditors may run in
  parallel;
- record target repo, target branch, starting SHA, worktree path, checks, and
  acceptance criteria.
- when a delegated contributor finishes, add a concise comment to the parent
  coordination card that summarizes the result, findings, decisions, blockers,
  and next steps; keep child-card comments/status for child-local execution
  details.

Treat different user requests, write scopes, and agents as separate
contributors in the card history. Do not bundle unrelated feature/fix work into
one implementation card because it arrived in the same prompt or because one
agent is available. A same-user local follow-up that continues the same object,
UI surface, domain concept, or cohesive topic may reuse the existing unmerged
topic branch while still creating or updating a distinct related card.

## Branch Discipline

Feature and fix implementation work must live on an explicit branch based on the
upcoming unreleased release branch and therefore ahead of `main`. Usually create
a card-named branch such as `feature/<CARD-ID>-short-title` or
`fix/<CARD-ID>-short-title`. Reuse an existing unmerged feature/fix branch
instead when all of these are true: the human's new local request is a follow-up
to the same object, UI surface, domain concept, or cohesive topic; it targets
the same release branch; it comes from the same immediate human/user context; and
reviewing it together would reduce duplicate edits or merge conflicts without
hiding unrelated behavior. In that case, create or update a related child/sibling
card, record the shared branch in `feature_branch`, add one or more focused
commits for the new card, and comment on the original/topic card when the
follow-up changes scope or review expectations. Create a new branch when the
request is unrelated, independently deployable/reviewable, from another release
or user context, owned by another writer, or broad enough to make the existing
topic branch unclear. Loose unstaged changes are not a valid handoff state.
Coordination, review, release, and read-only audit cards do not need their own
write branch, but they must record which implementation branch or release branch
they inspect.

Merge a feature/fix branch into the release branch only after human final
review/approval. After any approved card lands on the release branch, every
other active feature/fix branch for that release must rebase or otherwise
refresh from the release branch and record the updated base/handoff SHA and
checks before continuing.

After the feature branch and its release have landed in `main`, remove each
card-linked worktree with the guarded cleanup command. It preserves the
historical `worktree_path` on the card and refuses active cards, primary
checkouts, dirty worktrees, unrelated repositories, or branches that are not
ancestors of `main`:

```bash
PYTHONPATH="$KANBAN_REPO" python3 -m kanban_server.project worktree-cleanup \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  <numeric-card-id>
```

Use `--merged-branch <name>` only when the project's maintained integration
branch is not `main`. Worktree cleanup is part of the post-merge handoff; do
not leave merged card worktrees on disk indefinitely.

Avoid overlapping implementation cards. Treat these as conflict signals unless
the cards explicitly document an intentional same-user, same-topic branch share:

- same target repo/target branch without distinct feature branches;
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

For release work, `project_release_manager` and `kanban_auditor` are available
read-only profiles. The main agent may select either, another suitable agent,
or no subagent based on the release's scope and risk.

## Card Contract

Cards should accumulate only the fields needed for handoff:

- board/card ID, title, status, owner/assignee, priority, parent/child links;
- target repo/branch, start SHA, handoff SHA, feature branch, worktree path;
- affected paths, affected registered project paths, deployment dispositions;
- files changed, checks run, failures, assumptions, blockers;
- comments for human/agent feedback and follow-up child cards for separate
  work.
- parent-card comments for delegated contributor results that should remain
  with the topic context.

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

- update `CHANGELOG.md` and the AI-assistance disclosure when the project
  requires it; when the project requires exact disclosure, record every exact
  versioned model slug/named variant, the main or delegated roles that used it,
  and the short, unambiguous commit SHA of the installed/running Codex Kanban
  checkout that coordinated the release; reject base family slugs such as
  `gpt-5` and stop rather than infer missing runtime facts;
- audit tracked files and intended push refs for personal data, local paths,
  local databases, secrets, and generated coordination state;
- push only explicit release branches, the approved `main` release-merge
  fast-forward ref, or release tags; never `--mirror` or `--all` from a
  development repo;
- keep feature/fix work on explicit topic/card branches until human-approved
  merge to `release/<version>`, and keep release metadata commits on
  `release/<version>`;
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

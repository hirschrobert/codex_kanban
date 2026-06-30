---
name: codex-kanban
description: Coordinate project work through the local Codex Kanban dashboard with auditable cards, human-visible status, and optional multi-agent delegation. Use when a repo says to use Codex Kanban, when starting or decomposing implementation/review/release work, when registering a project board, when respecting human-added cards, or when coordinating multiple AI agents and handoffs.
---

# Codex Kanban

Use Codex Kanban as the shared coordination surface for humans, the main AI
agent, and subagents. Keep this skill generic: concrete domain, release,
deployment, accounting, security, and verification rules live in the current
repo's `AGENTS.md` and registered instruction files.

Use this coordination surface proportionally:

- No Kanban update is needed for trivial local operations, quick status checks,
  simple command output, or discussion that does not create or change project
  work.
- Light Kanban use is optional for exploratory design discussion. Use at most
  the relevant read-only specialist agents when they materially help, and do
  not create cards or move workflow unless the human asks to proceed or the
  discussion becomes concrete work.
- Full Kanban coordination is required for approved or concrete feature, fix,
  documentation, test, review, release, project-registration, or multi-agent
  work that changes files, plans implementation, hands work between agents, or
  affects project state.

## First Move

1. Read the current repo `AGENTS.md`, then the nearest nested `AGENTS.md`.
2. Find or register the project board. Prefer the server at
   `CODEX_KANBAN_URL` or `http://127.0.0.1:8766`; direct SQLite fallback is
   acceptable for local work.
   If the current repo `AGENTS.md` says to use `codex-kanban`, the hook should
   auto-register the repo when no active project matches the current path.
3. Inspect the board before starting work. Human-added cards are authoritative
   work requests unless the user explicitly redirects the task.
4. Select the relevant card or create a card when the requested work has no
   suitable card. A new card only needs title and description; other fields can
   be filled as the work becomes concrete.
5. Keep status visible: report start, block, handoff, and finish through the
   ingester or HTTP API.

Useful commands:

```bash
PYTHONPATH=/path/to/codex_kanban \
python3 -m kanban_server.project register \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --root <repo> \
  --slug <project-slug> \
  --display-name "<Project Name>" \
  --card-prefix <PREFIX>
```

```bash
PYTHONPATH=/path/to/codex_kanban \
python3 -m kanban_server.project list \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}"
```

```bash
PYTHONPATH=/path/to/codex_kanban \
python3 -m kanban_server.project snapshot \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --board <project-board-slug>
```

Create cards through the CLI when possible. Use `--why`, `--risk`, and
`--acceptance` so a human can tell why the card exists and what could go wrong
if it is skipped. When `card-create` has `--board` and no explicit
`--actor-id`, the CLI records the creator and owner as the board-scoped
`<project-board-slug>-ai-agent-manager` participant instead of the local human
developer:

```bash
PYTHONPATH=/path/to/codex_kanban \
python3 -m kanban_server.project card-create \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --board <project-board-slug> \
  --title "Review branch before merge" \
  --description "Inspect the feature branch for regressions before handoff." \
  --why "The implementation changed shared behavior and needs an independent read." \
  --risk "A subtle regression could be merged because the original implementer has context bias." \
  --acceptance "Reviewer records findings or explicitly marks the card done with checks run." \
  --assignee <registered-participant-id> \
  --check "python3 -m unittest discover -s tests"
```

Move or hand off cards through the CLI:

```bash
PYTHONPATH=/path/to/codex_kanban \
python3 -m kanban_server.project card-move <numeric-card-id> \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --status in_progress \
  --target-repo <repo-path> \
  --target-branch <upcoming-release-branch> \
  --feature-branch feature/<CARD-ID>-short-title \
  --worktree-path $HOME/codex-worktrees/<project-card> \
  --start-sha <target-sha-before-work> \
  --handoff-sha <target-sha-after-work> \
  --check "python3 -m unittest discover -s tests"
```

Use `--clear-blocker` when a blocker has been resolved and should be removed
from the card during a move or handoff. Passing `--blocker ""` also clears the
blocker text; omitting `--blocker` leaves any existing blocker text unchanged.

If an assignee is missing, register it first instead of inventing an id on the
card:

```bash
PYTHONPATH=/path/to/codex_kanban \
python3 -m kanban_server.project participant-upsert \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --board <project-board-slug> \
  --id <project-board-slug>-project-reviewer \
  --display-name project_reviewer \
  --kind agent \
  --status idle
```

```bash
PYTHONPATH=/path/to/codex_kanban \
python3 -m kanban_server.ingest \
  --board <project-board-slug> \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --event-type agent.started \
  --participant-id <project-board-slug>-<agent-profile> \
  --display-name <agent-or-human-name> \
  --participant-kind agent \
  --status running \
  --current-card-external-id <CARD-ID> \
  --current-scope "<repo/path or task scope>"
```

## Project Registration

Register single repos with one root path. Register ecosystems with repeated
`--path` and `--instruction` values so the hook can map a working directory to
the correct board and pass concrete instructions to subagents.

Use only abstract profiles by default:

- `kanban_auditor`
- `domain_model_steward`
- `architecture_impact_analyst`
- `api_contract_steward`
- `project_architect`
- `project_implementer`
- `project_reviewer`
- `project_release_manager`
- `test_strategist`

Project-specific agents belong in the project repo, usually
`<repo>/.codex/agents/`. Registration discovers project-local agent definition
files and seeds them as board-scoped participants. Treat those files as
project-local instructions and metadata, not as generic Kanban policy.

## Project-Scoped Agent Identities

Generic profiles are templates, not shared cross-project identities. Use
board-scoped participants for live work:

- `<project-board-slug>-kanban-auditor`
- `<project-board-slug>-domain-model-steward`
- `<project-board-slug>-architecture-impact-analyst`
- `<project-board-slug>-api-contract-steward`
- `<project-board-slug>-project-architect`
- `<project-board-slug>-project-implementer`
- `<project-board-slug>-project-reviewer`
- `<project-board-slug>-project-release-manager`
- `<project-board-slug>-test-strategist`

Do not assign a card on one board to a participant from another board. The
backend rejects cross-board assignees, participant card links, and event card
references. If a Kanban update fails with a board-scope error, correct the
board slug/card ID/participant ID instead of bypassing the Kanban update.

Kanban separates assignment from live activity. A card can remain assigned after
an agent stops heartbeating; snapshots and the UI mark stale active agents so a
human can see that work may no longer be live. Use heartbeats or event updates
when a delegated agent starts, waits, blocks, hands off, or finishes.

Default concurrency policy allows multiple projects to run agents at the same
time while limiting active workers inside one project:

- `CODEX_KANBAN_MAX_ACTIVE_AGENTS_PER_PROJECT=4`
- `CODEX_KANBAN_MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT=1` is the default for new
  or migrated projects
- `CODEX_KANBAN_MAX_ACTIVE_AGENTS_GLOBAL=0` means no Kanban-imposed global cap
- `CODEX_KANBAN_STALE_AFTER_SECONDS=300`

Codex itself must allow enough global subagent concurrency for cross-project
parallelism. Kanban enforces the project limits and treats stale agents as not
actively occupying a slot. Each project's active `project_implementer` limit is
stored in SQLite and editable in the dashboard Settings dialog; use `0` for
unlimited active implementers on that project.

## Multi-Agent Workflow

Use multiple AI agents when work naturally separates into independent planning,
implementation, review, release-readiness, documentation, or audit scopes.
Prefer subagents for parallel or specialist work, but keep the main agent
responsible for routing, integration, card hygiene, and the final user-facing
summary.

An instruction from the user or current repo to use Codex Kanban, together with
these multi-agent workflow rules, is an explicit request for coordinated
subagent delegation when that delegation is feasible and safe. Treat that as
permission to decompose work into cards, assign those cards to the registered
abstract profiles, and spawn well-scoped subagents when the current task
naturally benefits from independent implementation, review, release-readiness,
documentation, or audit work.

For Codex clients whose subagent tool says delegation needs an explicit user
request, the active use of this skill through a repo or user instruction is that
explicit request for the bounded Kanban workflow. Do not wait for the human to
repeat "spawn a subagent" before starting useful read-only reviewers,
architects, release managers, auditors, or non-overlapping implementers. Still
perform the tool's critical-path check first: keep immediate blocking work in
the main session, delegate sidecar or disjoint work, and avoid duplicate or
overlapping writes.

Release work should start a read-only `project_release_manager` or
`kanban_auditor` for the intake audit whenever a subagent tool is available and
the task is more than a trivial status check; if no subagent can be spawned,
record that limitation on the release card before doing the audit inline.

This permission is bounded by the board: create or update the relevant
parent/child cards first, use board-scoped participant IDs, respect active-agent
limits, and avoid overlapping write scopes. Actually spawning additional agents
still depends on the tools available in the current session. If subagent
spawning is not available, create or update the delegated cards anyway, then
continue the work in the main session and make the limitation visible in the
handoff.

When delegating, give each agent:

- board slug and card ID;
- role/profile and board-scoped participant ID to use;
- repo/path and file ownership scope;
- target branch or integration branch when relevant;
- starting target SHA if branch history matters;
- concrete task and acceptance criteria;
- required checks;
- explicit non-goals and approval boundaries from `AGENTS.md`;
- required handoff fields.

Avoid giving two agents overlapping write scopes. Use read-only reviewers and
auditors freely; use implementation agents only for bounded ownership.

Multiple cards may be in `in_progress`, but an agent must not treat every
in-progress card as its own work. The main/project agent chooses the current
card or explicitly coordinates a related set of cards, and makes that decision
visible on the board.

Parallel implementation cards are acceptable only when their write scopes do
not overlap. Treat these as conflict signals:

- same target repo and target branch;
- same feature branch;
- same worktree path;
- same declared files or ownership scope;
- missing target branch on an active implementation card.

If overlap is likely, move one card to `blocked` or `waiting` with the blocker
reason, or wait until the other card records a handoff SHA. Code integrity wins
over preserving local progress.

On this machine, feature branch worktrees should live under:

```text
$HOME/codex-worktrees
```

Before continuing unfinished feature-branch/worktree work after another card
lands, refresh the worktree from the current target branch and record the new
starting or handoff SHA. Active unfinished work should target the upcoming
unreleased release branch; if no such release branch exists, create one instead
of targeting `main` or `master`.

## Release Intake And Exclusion Audit

For release, deploy, or "merge releases to main" work, the release scope is all
completed, approved, or requested work ahead of the maintained integration
branch unless the human or project instructions explicitly exclude it. Do not
select only the card that is currently in focus.

Before preparing, reviewing, merging, tagging, publishing, or deploying a
release, perform a release intake audit for every registered repo in scope:

- enumerate release/prerelease branches and task branches ahead of the
  maintained integration branch;
- enumerate ready, in-progress, review, blocked, and done cards that target the
  release branch, repo, or a branch ahead of the integration branch;
- compare the cards, branches, and commits so each ahead-of-integration change
  has exactly one disposition: included in this release, explicitly excluded
  with a reason, or blocked with the blocker recorded;
- include done cards and reviewed implementation branches by default, even when
  they are not the newest card in the conversation;
- stop the release handoff if a done/approved card or ahead branch has no
  include/exclude disposition.

Record the intake result on the release card or handoff: included card IDs and
branches, excluded card IDs and branches with reasons, conflicts, checks, final
target SHA, and any dirty worktree changes intentionally excluded. When a
feature branch contains work for multiple cards, include the whole intended
branch or split/revert only with explicit human approval and a recorded reason.

## Card And Handoff Contract

A card should accumulate:

- board slug, card ID, title, status, assignee, priority, and parent/child
  links when useful. A parent depends on its child cards; in the generic
  dashboard policy the parent cannot move into `in_progress`, `review`, or
  `done` until every child dependency is `done`;
- target repo and target branch;
- starting target SHA and handoff target SHA for branch-sensitive work;
- feature branch and worktree path when used;
- files changed and why;
- checks run and exact failures;
- changed assumptions;
- blocker reason when human judgment, missing dependency, production access,
  destructive action, signing, security, legal, accounting, or scope ambiguity
  is involved;
- follow-up cards needed.

New cards should be understandable without reading the conversation transcript.
Prefer this description shape for non-trivial work:

- a short summary of the request;
- `Why this card exists:` one or two sentences tying the work to user-visible
  coordination, correctness, release, or maintenance value;
- `If this is not fixed:` concrete examples of what could go wrong;
- `Acceptance criteria:` observable conditions for moving the card forward or
  marking it done.

Example:

```text
The review agent could not create a card without falling back to raw HTTP.

Why this card exists:
Agents need a stable CLI path so coordination stays visible even when they do
not know the API routes.

If this is not fixed:
- An agent may skip Kanban updates after a failed HTTP request.
- A human may see a card title but not understand the risk the work is reducing.

Acceptance criteria:
- The CLI can list projects, inspect snapshots, create cards, and move cards.
- The skill shows a copyable example with checks and handoff fields.
```

Use an automatic continuous review loop for code work:

1. implementation card finishes with changed files, checks, target branch, and
   handoff SHA recorded;
2. the main/project agent immediately creates or moves the reviewer card to
   `in_progress` and starts a `project_reviewer` agent when the session has a
   delegation mechanism;
3. if no delegation mechanism is available, the main/project agent performs the
   review itself or leaves the reviewer card in `ready` with an explicit note
   that no reviewer could be started;
4. reviewer approval creates the final human merge/readiness checkpoint rather
   than another implementation card;
5. reviewer rejection creates or reopens a repair card assigned to
   `project_implementer` and starts/continues implementation automatically;
6. repair completion immediately starts a re-review card/agent;
7. repeat implementation -> review -> repair -> re-review until the reviewer
   says the formal specs, checks, and acceptance criteria are met;
8. sticky `blocked` is reserved for human approval, unsafe conflicts, missing
   dependencies, unclear product/domain judgment, production/destructive work,
   unavailable delegation when inline review is not appropriate, or repeated
   failed loops.

For larger feature cards, use specialist agents only when their concern is
relevant. Useful optional gates are:

- `domain_model_steward` for terminology and data model impact;
- `architecture_impact_analyst` for blast-radius notes;
- `api_contract_steward` before implementation when API/schema contracts are
  involved;
- `test_strategist` before or after implementation when test scope is unclear
  or high-risk.

Run independent specialists in parallel when their scopes are read-only or
otherwise non-overlapping. Do not spawn every profile by default, but do not
leave useful implementation, review, release, or audit delegation idle merely
because the human did not repeat the word "subagent" after selecting the Codex
Kanban workflow.

Recurring maintenance can be configured on cards with `Repeat` set to `daily`,
`weekly`, or `monthly` and a `Repeat Time` in `HH:MM`. The dashboard server
uses `Europe/Berlin` by default, checks due repeats once per minute, and creates
ready workflow cards only when the repeating template belongs to an active
registered project board and has an explicit target branch. When a scheduled
time is due, the server creates or reuses one ready workflow card and advances
the template to the next future run. Use the card's `Run Now` action when a
human intentionally wants an immediate workflow card. If a later repeat becomes
due while an older generated workflow card for the same recurring template is
still unfinished, Kanban must not create another ready card; it comments on the
existing workflow card with the due schedule date/time and advances the template
to the next future run.

Card comments are the generic place for human or agent notes that future work
should consider. Keep them project/card scoped; do not hardcode
domain-specific note types into the dashboard.

The dashboard server itself creates coordination cards only. It must not be
treated as permission for Codex CLI execution, commits, releases, production
deploys, or other project-specific automation unless the current project
`AGENTS.md` and human approval boundaries allow that automation.

When a concrete implementation/review run changes files on an active release
branch, and the repo instructions plus human approval boundaries allow commits,
finish the run by committing the verified changes on that release branch before
closing the parent card. Record the commit SHA and checks on the relevant
implementation/review cards. Do not invent commits for read-only, exploratory,
blocked, no-change, production, publish, or destructive work.

A human or OS cron can explicitly trigger queued workflow work with the local
CLI. Without `--execute` the command is a dry run; with `--execute` it launches
`codex exec` for ready workflow cards. With `--board`, only that project board
is scheduled and executed; without `--board`, all active project boards may be
scheduled and executed. Use repeated `--card <id-or-external-id>` arguments to
run only specific ready workflow cards. The runner resolves target repos from
the card or registered project, prepares the card's target release branch in the
registered project repo(s), refuses `main` and `master`, marks successful runs
`done`, and marks failed or unsafe runs `blocked`:

```bash
PYTHONPATH=/path/to/codex_kanban \
python3 -m kanban_server.project due-run \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --board <project-board-slug> \
  --execute
```

External cron/systemd timers may also start recurring maintenance work through
the generic CLI/API workflow starter. Require an explicit target branch, or use
the git-current-branch flag only when that branch is the current release branch:

```bash
PYTHONPATH=/path/to/codex_kanban \
python3 -m kanban_server.project workflow-start \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}" \
  --board <project-board-slug> \
  --workflow-key docs-refresh \
  --scheduled-for "$(date -u +%F)" \
  --title "Refresh stale documentation" \
  --description "Check docs and descriptions for drift from recent changes." \
  --target-repo <repo-path> \
  --target-branch <current-release-branch> \
  --assignee <project-board-slug>-project-implementer
```

Humans should normally be interrupted only for final merge/readiness decisions
after reviewer approval, or for real blocker/approval boundaries from the
project `AGENTS.md`. A reviewer suggestion to merge is not itself approval to
merge; it is the point where the human can make the final decision.

## Approval Boundaries

Never treat the Kanban card itself as approval for risky actions. Follow the
current repo's `AGENTS.md` and ask the human before production changes,
destructive operations, migrations, package publishing, release tagging,
credential handling, or other project-specific approval gates.

Do not invent domain rules. If a domain conclusion is unclear, create or block
a card for human/project-specialist review.

## Final Response

Summarize the card IDs touched, agents used, changed files, checks, failures,
and follow-up cards. If no Kanban update was possible, say why and include the
intended card/status update in the final response.

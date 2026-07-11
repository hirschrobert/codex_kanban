# Codex Kanban Dashboard

This is a Codex-native realtime Kanban dashboard for human and AI coordination.
It stores board state in SQLite and avoids writing unrelated coordination
state.

The Kanban app is intentionally generic. Concrete project rules stay in each
project repository, normally in `AGENTS.md`; project registration records only
point the dashboard and hooks at those instruction files.

## Run

```bash
python3 -m kanban_server --host 127.0.0.1 --port 8766
```

Open:

```text
http://127.0.0.1:8766
```

The default port is `8766` to avoid colliding with local OAuth callback
fixtures that commonly bind `8765`.

The default database path is:

```text
$HOME/.codex/codex-kanban/kanban.sqlite3
```

Override it with:

```bash
CODEX_KANBAN_DB=/path/to/kanban.sqlite3 python3 -m kanban_server
```

On graceful shutdown, including Ctrl+C in a Linux terminal, the server prunes
event rows older than 48 hours from the SQLite database. Cards and card
comments are retained.

When running CLI examples from a source checkout, set `KANBAN_REPO` to the
checkout that contains `kanban_server`. From inside this repository the Git root
fallback is enough; from another project, set `CODEX_KANBAN_REPO` first:

```bash
KANBAN_REPO="${CODEX_KANBAN_REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
test -d "$KANBAN_REPO/kanban_server" || {
  echo "Set CODEX_KANBAN_REPO to the codex_kanban checkout"
  exit 1
}
```

## Clean Local Database

Reset the SQLite database while preserving the schema:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project reset --yes
```

After a reset, register the desired projects again so they appear in the
dashboard dropdown.

## Startup Overview

Agents should start with the lean workspace overview instead of a full board
snapshot:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project overview \
  --server-url http://127.0.0.1:8766 \
  --cwd "$PWD" \
  --repo "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" \
  --done-limit 5 \
  --register-if-missing
```

The overview resolves the current repo or ecosystem path to the registered
board, lists all non-done non-archived cards with descriptions, includes only
the latest five done cards by default, includes affected registered project
paths, and reports how many archived and done cards are hidden. Use
`--done-limit -1` when completed-card history matters, and use `--archived-only`
when older archived context may matter. `--register-if-missing` only
auto-registers a single repo whose `AGENTS.md` opts into `codex-kanban`;
ecosystems still need explicit repeated `--path` and `--instruction` values.
The same overview also refreshes board-scoped AI participants from current
generic/default profiles and discoverable project-local `.codex/agents`, so the
dashboard people, owner, assignee, and comment-writer fields stay current after
agent defaults or project agents change.

## Manual Dialogs

The primary intake path is conversational: a human gives a feature request,
error report, or release concern to the main AI agent for the project. The main
agent records the request as one or more cards, chooses the relevant
board-scoped participants, and then coordinates implementation, review, CI, and
release-readiness handoffs through the board.

Direct dashboard entry is optional. It is useful when a human wants to seed a
card without starting an agent session yet, but it is not required for normal
continuous development.

For a new card, fill only:

- `Title`: short task name.
- `Description`: concrete request, acceptance criteria, or enough context for a
  human or agent to know what done means.

All other card fields are optional. `Intake` can mark a feature request, error
report, coordination task, maintenance task, review, or release item. `Source`
can distinguish main-agent intake from dashboard, CLI, or automation-created
cards. `Reported By`, `Impact`, `Affected Paths`, and `Evidence` preserve
human context so another agent can continue without reading the chat
transcript. For ecosystem work, `Affected Paths` should name every implicated
app, repo, worktree, or file path. `Deployment Dispositions` records the
release/deploy checklist, for example
`Portal|/workspace/portal=deployed:0.2.17 live` or
`Backend|/workspace/db_worker=not_required:unchanged`. `Status` defaults to
`Backlog`, `Priority` defaults to `Normal`, `Repeat` defaults to `None`, and
`Assignee` can stay unassigned until a human or agent takes the card. Branch,
repo, SHA, blocker, and checks fields are for later handoffs or specialist work.

Split multi-intent intake before implementation starts. If one human message
contains independent features, fixes, apps, repos, user roles, UI flows, or
deployment scopes, create separate task cards. Use a parent coordination card
plus child cards when the tasks share one release or branch context; otherwise
use sibling cards. One implementation card should not bundle unrelated
deliverables just because they arrived in one prompt.

Cards can also be linked as dependencies. A parent card depends on its child
cards. In the generic dashboard policy, a parent cannot move into
`in_progress`, `review`, or `done` until every child dependency is `done`.
This is stricter than "not blocked": a child that is ready or in progress is
still unfinished prerequisite work. The backend enforces this rule for the UI,
CLI, and HTTP API.

When a card moves into active implementation, set `Target Branch` to the
upcoming release branch that has not been released yet. If the project has no
such release branch, create one. Workflow automation must not target `main` or
`master`. Feature or fix implementation cards should also record a
`Feature Branch`, usually `feature/<CARD-ID>-short-title` or
`fix/<CARD-ID>-short-title`, created from the target release branch and ahead of
`main`. If a same-user local follow-up continues the same object, UI surface,
domain concept, or cohesive topic on an unmerged branch, reuse that branch and
record it on the related child/sibling card instead of creating a competing
branch. Create a new feature branch for unrelated, independently reviewable,
different-release, or different-owner work. Coordination, review, release, and
read-only audit cards can omit their own write branch, but they should record
which implementation branch or release branch they inspect.
By convention, feature branches or worktrees can live under:

```text
$HOME/codex-worktrees
```

Linked Git worktrees retain the identity of their primary repository. Opening
or running an overview inside a linked worktree resolves to the project board
registered for the primary checkout instead of registering a new project. On
cards, use `Target Repo` for that primary checkout and `Worktree Path` for the
checkout that contains the actual changes. The card then shows the worktree as
its change source while remaining on the primary project's board.

After the feature branch and release have landed in `main`, remove the clean
linked worktree and record that cleanup on the card:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project worktree-cleanup \
  --server-url http://127.0.0.1:8766 \
  123
```

The cleanup command requires a done card with `target_repo`, `feature_branch`,
and `worktree_path`. It verifies that the path is a non-primary worktree of the
same repository, the worktree is clean, and the feature branch is an ancestor
of `main` before running `git worktree remove`. Repeating the command after a
successful removal is safe. Use `--merged-branch` for projects whose maintained
integration branch has another name.

Repeating cards are schedule templates. Choose `Daily`, `Weekly`, or `Monthly`
and a `Repeat Time` in `HH:MM`; the default is `01:00` in `Europe/Berlin`.
Repeating cards must live on an active registered project board and have
`Target Branch` set so generated workflow cards stay on the current release
branch. The running dashboard server checks due repeats once per minute. If a
scheduled time is already due when the server or `due-run` checks it, the
server creates or reuses one ready workflow card and advances the template to
the next future run. Use the card's `Run Now` button when a human intentionally
wants an immediate workflow card.

Card notes capture human or agent context that future work should consider but
that is not a separate task. Use them for findings, decisions, blockers,
readiness context, and contributor results. Notes are scoped to the card's board
and appear in the card dialog with writer name, writer kind, date, and time.
Agent `finished`, `feedback`, and `handoff` events, plus hook-style subagent
`stopped`, `feedback`, and `handoff` events, are mirrored into notes when they
include a card and message so card owners do not need to scan the event stream
for delegated feedback.

For parent/child coordination, child cards hold execution state: assignee,
branch/worktree, files changed, checks, blockers, and handoff SHA. The parent
coordination card should hold the durable topic context. When a subagent or
other contributor finishes material work, add a concise note to the parent card
with its result, findings, decisions, blockers, and next steps. This keeps the
parent card useful as the place where future agents resume the topic.

Archived cards are hidden from the normal board. Use the top-bar `Archived`
toggle to switch to archived cards only; non-archived cards are hidden in that
view. In normal board view, check cards and use `Archive` to archive the
checked cards. In archived view, archived cards start checked; deselect the
archived cards you want to restore and use `Unarchive`. Only archived cards can
be deleted.

For non-trivial cards, write the description so it is useful without reading the
chat transcript:

- Start with the request or observed problem.
- Add `Why this card exists:` and explain the coordination, correctness,
  release, or maintenance value.
- Add `If this is not fixed:` with concrete examples of what could happen.
- Add `Acceptance criteria:` when there is a clear done condition.

Use either those headings in the description or the CLI `--why`, `--risk`, and
`--acceptance` helpers. Do not use both for the same section; later feedback
belongs in notes, and separate work belongs in a child card or new sibling card
before implementation is assigned.

For a person, fill:

- `Name`: the visible name. The internal ID is generated from this.
- `Status`: usually `Idle` unless the person is actively working, waiting,
  blocked, or offline.

Agent role and scope are maintained by hooks/heartbeats and are not required
when adding people manually.

## Event Ingestion

Wrapper scripts and Codex hooks can report status through the HTTP API:

```bash
CODEX_KANBAN_URL=http://127.0.0.1:8766 \
python3 -m kanban_server.ingest \
  --board my-project \
  --event-type subagent.started \
  --participant-id my-project-project-implementer \
  --display-name project_implementer \
  --participant-kind agent \
  --status running \
  --message "Started implementation card" \
  --current-card-external-id MY-0001 \
  --current-scope "/path/to/my-project"
```

If no board is supplied, the ingester maps `--cwd` to the registered project
whose root/path contains it. If `CODEX_KANBAN_URL` is not set, the ingester
writes directly to SQLite. Direct SQLite writes are picked up by the browser
polling fallback; HTTP writes update open dashboards immediately through
Server-Sent Events.

## Project-Scoped Agents And Liveness

Generic agent profiles are reusable templates only. Each registered project gets
board-scoped participant identities such as:

```text
my-project-project-implementer
my-project-project-reviewer
```

The People panel shows these durable roles, not raw Codex thread or spawned
agent IDs. Fresh hook events are grouped under their role as live runtime
instances, including their authoritative status, current card/scope, and model
when Codex reports it. Multiple concurrent instantiations of one role appear
under that single role. A `SubagentStop` or turn `Stop` removes the instance
from the live overview immediately; instances without a fresh event age out
after the configured stale interval. Roles remain available and idle after all
their instances finish, while the retained Activity events preserve the audit
trail and per-turn model history.

The backend rejects cross-board mistakes:

- a card on board `B` cannot be assigned to board `A`'s agent;
- participant heartbeats cannot point at a card from another board;
- events with a card ID or card external ID must resolve on the event board;
- events cannot use a board-scoped participant from another board.

This keeps `project_implementer` for project A from accidentally starting or
owning review/implementation cards for project B.

Kanban separates assignment from active liveness. A card can remain assigned to
an agent after the last heartbeat, but snapshots and the UI mark the agent/card
stale when no active heartbeat was seen recently. Configure server-wide
liveness and global/default concurrency before starting the server:

```bash
CODEX_KANBAN_STALE_AFTER_SECONDS=300 \
CODEX_KANBAN_MAX_ACTIVE_AGENTS_PER_PROJECT=4 \
CODEX_KANBAN_MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT=1 \
CODEX_KANBAN_MAX_ACTIVE_AGENTS_GLOBAL=0 \
python3 -m kanban_server --host 127.0.0.1 --port 8766
```

`CODEX_KANBAN_MAX_ACTIVE_AGENTS_GLOBAL=0` means Kanban does not impose a global
cap, so different projects can run agents concurrently.
`CODEX_KANBAN_MAX_ACTIVE_IMPLEMENTERS_PER_PROJECT` is only the default for new
or migrated projects. Each registered project's active implementer limit is
stored in SQLite and can be edited in the Settings dialog without restarting
Kanban. Codex itself must allow enough global agent concurrency for the desired
cross-project parallelism; Kanban owns the project guardrails.

## Project Registration

Projects register a board plus concrete instruction paths:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project register \
  --server-url http://127.0.0.1:8766 \
  --root /path/to/my-project \
  --slug my-project \
  --display-name "My Project" \
  --card-prefix MY
```

Registered projects appear in the dashboard project dropdown. Human-created
cards on a project board are first-class work items: agents must respect them
and should not silently bypass the selected card/scope.

If a repo `AGENTS.md` says to use the `codex-kanban` skill and the hook sees
work starting from that repo before it has an active board, the hook
auto-registers a minimal project entry from the repo root, name, and
`AGENTS.md` path.

For ecosystems, repeat `--path` and `--instruction`:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project register \
  --server-url http://127.0.0.1:8766 \
  --root /workspace/main-repo \
  --slug my-ecosystem \
  --display-name "My Ecosystem" \
  --card-prefix ECO \
  --path "Backend=/workspace/main-repo/backend" \
  --path "Frontend=/workspace/frontend" \
  --instruction /workspace/main-repo/AGENTS.md \
  --instruction /workspace/frontend/AGENTS.md
```

To generate a prompt/command for a new project's main AI agent:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project prompt \
  --root /path/to/my-project \
  --display-name "My Project" \
  --card-prefix MY
```

Put this durable instruction in a new project's `AGENTS.md`:

```markdown
## Codex Kanban

- Use the `codex-kanban` skill for concrete feature, fix, docs, test, review,
  release, registration, or multi-agent work in this repository.
- Treat Codex Kanban as a standing instruction to consider specialized
  subagents at session start and before material implementation, review,
  release-readiness, documentation, audit, domain, contract, architecture, or
  test-strategy work. Use them when they can improve software quality,
  usability, safety, maintainability, or data integrity. Choose relevant
  specialists from all available board-scoped profiles, including project-local
  profiles, instead of spawning every profile by default, and explain why
  delegation was used or skipped.
- Treat different user requests, implementation scopes, and agents as separate
  contributors in cards and comments. Same-user local follow-ups that continue
  the same object or cohesive topic may share the existing unmerged branch, with
  each card recording that branch and contributing focused commits before
  handoff. Unrelated or independently reviewable work needs a new branch. Merge
  feature/fix branches to the release branch only after human final review, then
  rebase or refresh remaining active feature/fix branches from that release
  branch.
- Do not create Kanban cards or workflow updates for trivial local operations,
  quick command checks, or discussion that does not change project work.
- For exploratory feature discussion, Kanban is optional and should stay light:
  use only relevant read-only agents when helpful, and wait for human approval
  before turning ideas into implementation cards.
```

## Agent CLI

Agents should prefer the CLI over raw HTTP when they need to inspect or update
the board:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project list \
  --server-url http://127.0.0.1:8766
```

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project overview \
  --server-url http://127.0.0.1:8766 \
  --cwd "$PWD" \
  --repo "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" \
  --done-limit 5 \
  --register-if-missing
```

Use `snapshot` when an agent needs full events, participants, comments, or an
archived-inclusive board view.

Create a human-readable card with concrete context:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project card-create \
  --server-url http://127.0.0.1:8766 \
  --board my-project \
  --title "Review branch before merge" \
  --description "Inspect the feature branch for regressions before handoff." \
  --why "The implementation changed shared behavior and needs an independent read." \
  --risk "A subtle regression could be merged because the implementer has context bias." \
  --acceptance "Reviewer records findings or marks the card done with checks run." \
  --assignee my-project-project-reviewer \
  --check "python3 -m unittest discover -s tests"
```

When the main AI agent receives a human feature request or error report, add
intake metadata while creating the card:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project card-create \
  --server-url http://127.0.0.1:8766 \
  --board my-project \
  --title "PDF preview fails" \
  --description "Opening an uploaded PDF shows a blank panel." \
  --intake-kind error_report \
  --reported-by "Front desk" \
  --impact "Blocks invoice review." \
  --evidence "Observed in the desktop client after selecting a recent upload." \
  --affected-path /workspace/my-project/app \
  --affected-path /workspace/my-project/backend \
  --assignee my-project-project-implementer \
  --target-branch release/current \
  --check "python3 -m unittest discover -s tests"
```

When `card-create` includes `--board` and no explicit `--actor-id`, the CLI
creates or reuses `<board>-ai-agent-manager` and records that agent as the card
creator and owner. It also defaults `intake_source` to `main_agent`, matching
the normal conversational intake path. Use `--actor-id` when a specific
board-scoped agent is doing the work, or create cards through the dashboard
when the local human developer is the creator.

Move or hand off a card:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project card-move 1 \
  --server-url http://127.0.0.1:8766 \
  --status in_progress \
  --target-repo /path/to/my-project \
  --target-branch release/1.2 \
  --feature-branch feature/MY-0001-review \
  --worktree-path $HOME/codex-worktrees/my-project-my-0001 \
  --start-sha <target-sha-before-work> \
  --handoff-sha <target-sha-after-work> \
  --check "python3 -m unittest discover -s tests"
```

Use `--clear-blocker` when a resolved blocker should be removed while moving
or handing off a card. Passing `--blocker ""` also clears the blocker text;
omitting `--blocker` leaves existing blocker text unchanged.

For feature/fix work, the `--feature-branch` value should point to the branch
that contains the card's commits. It is usually unique to the implementation
card, but it may intentionally match another unmerged card when the newer card
is a same-user local follow-up on the same object or cohesive topic and shared
review reduces duplicate edits or conflicts. Do not hand off unstaged
implementation files. After a human-approved merge updates the release branch,
refresh every other active feature/fix branch from that release branch before
more edits and record the new SHA/checks.

Add a durable note to a card:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project card-comment 1 \
  --server-url http://127.0.0.1:8766 \
  --board my-project \
  --participant-id my-project-project-reviewer \
  --body "Reviewer result: no blocking findings; run contract tests before merge."
```

Use `card-comment` when the information should stay with the card but should
not become a separate task. If a delegated agent finishes work on a child card,
write the result summary on the parent coordination card and keep the child
card's move/check/handoff fields focused on execution details.

Link dependency cards from the CLI:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project card-create \
  --server-url http://127.0.0.1:8766 \
  --board my-project \
  --title "Implement API client" \
  --description "Implement the client after the API contract is done." \
  --child MY-0002
```

## Scheduled Workflow Starters

For dashboard-managed schedules, set `Repeat` on a card in an active registered
project. For external schedulers such as cron or systemd timers, call the
generic workflow starter. The starter creates one card per board, workflow key,
and scheduled date; a second call with the same key/date returns the existing
card. If the next repeat becomes due while an older generated workflow card is
still unfinished, Kanban does not create a second ready card. It adds a system
note to the existing workflow card with the missed schedule date/time and
advances the template to its next future run.

The dashboard server does not execute `codex` or spawn agents by itself. It
creates auditable ready cards that the normal Codex Kanban workflow, hooks, or
human-approved local automation can pick up according to the project
`AGENTS.md`.

To list due ready workflow cards and the `codex exec` command that would run
them:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project due-run \
  --server-url http://127.0.0.1:8766 \
  --board my-project
```

To execute them from a trusted shell or OS cron, add `--execute`:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project due-run \
  --server-url http://127.0.0.1:8766 \
  --board my-project \
  --execute
```

`due-run` asks the server/store to materialize due repeating templates into
ready workflow cards, then runs ready cards created through `workflow_runs`
with `codex exec --cd <target-repo>`. With `--board`, only that board is
scheduled and executed; without `--board`, all active project boards may be
scheduled and executed. Add `--card <id-or-external-id>` one or more times to
run only specific ready workflow cards.

Before launching Codex, `due-run` resolves the target repo from the card or its
registered project and prepares the card's target release branch in every
registered git repo for that project. It refuses `main` and `master`, blocks the
card if the repo or branch scope is unsafe, marks cards `in_progress` before
launching Codex, marks successful runs `done`, and marks failed runs `blocked`.
Without `--execute` it is a dry run.

Require the current release branch explicitly:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project workflow-start \
  --server-url http://127.0.0.1:8766 \
  --board my-project \
  --workflow-key docs-refresh \
  --scheduled-for "$(date -u +%F)" \
  --title "Refresh stale documentation" \
  --description "Check docs and descriptions for drift from recent changes." \
  --target-repo /path/to/my-project \
  --target-branch release/current \
  --assignee my-project-project-implementer \
  --check "python3 -m unittest discover -s tests"
```

Use `--target-branch-from-git` only when the current checked-out branch is the
intended release branch for that project. The starter only creates coordination
cards; project `AGENTS.md` still controls whether an agent may edit files,
commit, publish, migrate, sign, deploy, or ask for human approval.

## Release Integration

For public releases, feature and fix cards first live on explicit topic/card
branches. Same-topic follow-up cards may share one unmerged branch when they are
reviewed as a cohesive change. After human final review, merge approved
feature/fix branches into `release/<version>` and rebase or otherwise refresh
the remaining active feature/fix branches from that updated release branch. Keep
release metadata commits directly on `release/<version>`. Create the
no-fast-forward merge commit locally before the first public push for that
release. The merge commit should use the current public `main` as first parent
and the release branch tip as second parent. Push that merge commit to
`release/<version>` once
and wait for CI on that exact SHA, then fast-forward `main` to the same merge
SHA and tag that merge commit.

This keeps `main` easy to scan by release merge points while preserving the
release branch as the visible group of included work. It also avoids a CI run
on the pre-merge release tip followed by a second run on almost the same merge
tree. Do not squash, rebase, rewrite, or create a separate untested main-only
commit for release integration.

If a card assignment fails because the assignee is unknown, choose an existing
participant from the snapshot or register the participant first:

```bash
PYTHONPATH="$KANBAN_REPO" \
python3 -m kanban_server.project participant-upsert \
  --server-url http://127.0.0.1:8766 \
  --board my-project \
  --id my-project-project-reviewer \
  --display-name project_reviewer \
  --kind agent \
  --status idle
```

## Settings

The dashboard Settings dialog lists active and removed projects, shows the
current agent liveness/concurrency policy, and lets humans change each
project's active `project_implementer` limit. Use `0` for unlimited active
implementers on that project.

- `Remove` soft-removes a project from the normal project picker. Cards, events,
  participants, and project metadata stay in SQLite and reappear if the project
  is registered again.
- `Prune` permanently removes the project board and its cards, events,
  participants, and registration metadata.

## API

- `GET /api/snapshot?board=<board_slug>`
- `GET /api/snapshot?board=<board_slug>&archived_only=1`
- `GET /api/snapshot?board=<board_slug>&include_archived=1`
- `GET /api/overview?cwd=<path>&repo=<path>`
- `GET /api/overview?cwd=<path>&archived_only=1`
- `GET /api/projects`
- `GET /api/events/stream?board=<board_slug>`
- `GET /api/events/stream?board=<board_slug>&archived_only=1`
- `POST /api/projects`
- `POST /api/projects/{slug}/remove`
- `POST /api/projects/{slug}/prune`
- `POST /api/cards`
- `PATCH /api/cards/{id}`
- `DELETE /api/cards/{id}` for archived cards
- `POST /api/cards/{id}/run-now` for repeating cards
- `POST /api/cards/{id}/comments`
- `POST /api/workflows/start`
- `GET /api/workflows/due-cards?board=<board_slug>`
- `POST /api/workflows/due`
- `POST /api/participants`
- `POST /api/participants/{id}/heartbeat`
- `POST /api/events`

Cards keep cross-project handoff fields such as target repo, target branch,
starting and handoff SHAs, feature branch, blocker reason, changed files,
checks, changed assumptions, and follow-up cards.

## Agent Contract

Participating AI agents should:

- check the selected board for human-added cards before starting work;
- rerun the startup overview when a session starts or the human asks to reload
  `codex-kanban`; this refreshes current generic/default and project-local AI
  agents into the UI people fields before cards are assigned;
- use board-scoped participant IDs such as
  `<board-slug>-project-implementer`; generic profile names are templates, not
  cross-project identities;
- work only on their assigned card/scope unless the user explicitly redirects
  them;
- respect Kanban's active-agent limits. Different project boards can run agents
  concurrently, but a project should normally have only one active
  `project_implementer` unless the server policy is changed;
- treat multiple `in_progress` cards as allowed but not automatically assigned
  to the same agent; the main/project agent decides whether to coordinate more
  than one card, and should say so visibly;
- avoid parallel implementation work with overlapping write scope. Overlap
  means the same target repo/branch without distinct feature branches, same
  feature branch, same worktree path, or same declared files. If overlap is a
  same-user local follow-up on the same object or cohesive topic, continue on
  the existing unmerged branch and record the shared branch on each related card;
  otherwise block or wait one card until the other card records a handoff SHA;
- give each feature/fix implementation topic an explicit branch with one or more
  focused commits before handoff. Do not combine unrelated cards on one branch
  and do not treat loose unstaged files as handoff state;
- refresh feature branches/worktrees from the current target branch before
  continuing unfinished work after another card lands. Integrity of the
  integrated codebase takes priority over preserving local progress;
- set the active card's target branch to the upcoming unreleased release branch,
  creating that release branch when needed instead of using `main` or `master`;
- split multi-intent human requests into separate cards before implementation:
  one feature plus one fix, different affected apps, different user roles, or
  independent deployment scopes should not share one implementation card;
- treat Codex Kanban as a standing instruction to consider specialized
  subagents at session start and before material implementation, review,
  release-readiness, documentation, audit, domain, contract, architecture, or
  test-strategy work. Use them when they can improve software quality,
  usability, safety, maintainability, or data integrity. Choose the smallest
  useful set from all available board-scoped profiles, including project-local
  profiles, instead of spawning every profile by default, and explain why
  delegation was used or skipped;
- start review automatically after implementation cards complete when a
  delegation mechanism is available. The implementation agent should not leave a
  reviewer card merely `ready` unless no reviewer can be started;
- continue rejected reviews automatically: reviewer findings create or reopen a
  repair card for `project_implementer`, repair completion starts re-review, and
  the loop repeats until formal specs, checks, and acceptance criteria pass;
- reserve human intervention for final merge/readiness decisions after reviewer
  approval, or for real blockers/approval gates from the project `AGENTS.md`.
  A reviewer recommendation to merge is not itself merge approval;
- treat dependency links as release guards: a parent depends on its child cards,
  and the parent may advance only after its children are done;
- write durable findings, decisions, blockers, and contributor results as card
  comments. When a delegated contributor finishes, summarize its result on the
  parent coordination card so the parent keeps the topic context;
- move or report the card when they start, block, hand off, or finish;
- include card ID, branch, before/after target SHAs, changed files, checks,
  failures, changed assumptions, and follow-up cards in handoffs;
- read the concrete project `AGENTS.md` files registered for the selected
  project.

Some Codex subagent tooling may still reject spawning from standing repo or
skill instructions alone. This behavior is tracked in
<https://github.com/openai/codex/issues/18994>. When a workflow would benefit
from subagents but the active Codex environment disallows spawning, record the
coordination cards and surface the blocker instead of doing delegated work
silently in the parent context.

## Abstract Agent Profiles

Reusable profiles live in `.codex/agents/` in this repository, or
`$HOME/.codex/agents/` after installation:

- `kanban_auditor`: read-only card, handoff, stale-state, branch, and release
  containment audit.
- `domain_model_steward`: read-only terminology, ubiquitous-language, and data
  model impact review.
- `architecture_impact_analyst`: read-only blast-radius, boundary, and
  architectural impact analysis.
- `api_contract_steward`: read-only OpenAPI, AsyncAPI, schema, and
  contract-first review.
- `project_architect`: read-only architecture, contracts, release implications,
  and implementation decomposition.
- `project_implementer`: bounded implementation worker.
- `project_reviewer`: read-only correctness, regression, security, and test
  review.
- `project_release_manager`: read-only release and CI/CD integration review.
- `test_strategist`: read-only test strategy, coverage, and verification
  planning.

Project-specific agents can still exist, but they should not be seeded on every
board by default. The default CI/CD flow should use these abstract profiles and
let each repo's `AGENTS.md` provide concrete commands and constraints.
The packaged TOML definitions omit `model`, so spawned agents inherit the model
used by the calling Codex session instead of pinning a release-specific model.
Inheritance is the default, not a requirement: when the active Codex surface
supports per-agent selection, the main agent may request a supported lighter
model for bounded low-risk scans, triage, or summarization while retaining the
current stronger model for ambiguous implementation, architecture, release,
security, and data-integrity work. People reports the actual hook-supplied
runtime model for each live instantiation and summarizes all active models on
the stable role row.

For OpenAI or Codex documentation lookup, use the bundled OpenAI Docs
skill/agent from Codex instead of registering a duplicate global profile.

Project-specific extensions belong in the project repository, for example:

```text
<repo>/.codex/agents/<project-agent>.toml
```

Registration and hook auto-registration discover `.toml`, `.json`, `.md`, and
`.txt` files in `.codex/agents/` under the project root and registered project
paths. The dashboard registers their profile names as board-scoped participants
only; the project-local files and `AGENTS.md` remain the source of domain
policy. The Kanban hook passes the registered profile list to spawned subagents
as context and maps matching local subagents to board-scoped participant IDs.

## Hook Shape

Codex hook configuration should call the hook adapter rather than writing
unrelated local state. A user-level hook can live at `$HOME/.codex/hooks.json`
and call `python3 -m kanban_server.hook` for `UserPromptSubmit`,
`SubagentStart`, `SubagentStop`, and `Stop`. Codex includes the active `model`
in every hook payload and includes `turn_id` on turn-scoped hooks, so the
adapter records the actual model for each turn even when the user changes
models during one session. Codex may require reviewing/trusting that hook with
`/hooks` before it runs.

A project-local hook can be based on this shape after review/trust:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "test -d \"${CODEX_KANBAN_REPO:?Set CODEX_KANBAN_REPO to the codex_kanban checkout}/kanban_server\" && CODEX_KANBAN_URL=http://127.0.0.1:8766 PYTHONPATH=\"$CODEX_KANBAN_REPO\" python3 -m kanban_server.hook"
          }
        ]
      }
    ],
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "test -d \"${CODEX_KANBAN_REPO:?Set CODEX_KANBAN_REPO to the codex_kanban checkout}/kanban_server\" && CODEX_KANBAN_URL=http://127.0.0.1:8766 PYTHONPATH=\"$CODEX_KANBAN_REPO\" python3 -m kanban_server.hook"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "test -d \"${CODEX_KANBAN_REPO:?Set CODEX_KANBAN_REPO to the codex_kanban checkout}/kanban_server\" && CODEX_KANBAN_URL=http://127.0.0.1:8766 PYTHONPATH=\"$CODEX_KANBAN_REPO\" python3 -m kanban_server.hook"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "test -d \"${CODEX_KANBAN_REPO:?Set CODEX_KANBAN_REPO to the codex_kanban checkout}/kanban_server\" && CODEX_KANBAN_URL=http://127.0.0.1:8766 PYTHONPATH=\"$CODEX_KANBAN_REPO\" python3 -m kanban_server.hook"
          }
        ]
      }
    ]
  }
}
```

Install or refresh the same four lifecycle hooks at user scope with:

```bash
PYTHONPATH="$CODEX_KANBAN_REPO" python3 -m kanban_server.hook install \
  --repo "$CODEX_KANBAN_REPO" \
  --server-url "${CODEX_KANBAN_URL:-http://127.0.0.1:8766}"
```

The installer preserves unrelated handlers and already installed Codex Kanban
handlers so existing trust records remain stable, and adds missing lifecycle
events. Review/trust the new `UserPromptSubmit` hook with
`/hooks`; start a new Codex session if the current client does not reload hook
configuration dynamically.

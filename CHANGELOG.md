# Changelog

## 0.1.13 - 2026-07-11

This release makes specialist-agent liveness resilient when Codex reports an
untyped `default` subagent, while making exact custom-agent selection an
explicit prerequisite for delegation.

Public commits:

- `0f06ea5` binds an untyped subagent to the sole pre-activated specialist role,
  keeps ambiguous starts unbound, preserves the reported runtime type and
  binding source, and closes the lifecycle by exact runtime ID.
- `a165892` requires Codex Kanban delegation to select and verify the exact
  custom-agent `name`, distinguishes agent type from `task_name`, and forbids
  presenting a `default` agent as a named specialist whose TOML was not loaded.
- `7249fa4` merges CK-0685 and CK-0686 into `release/0.1.13` after human
  approval.

Release metadata note:

The release metadata commit that updates this changelog and bumps package
version files is not self-referenced; this follows the existing changelog
convention for avoiding unstable self-hashes.

Changes:

- Restored the People live indicator for an untyped subagent when exactly one
  board-scoped non-manager role was explicitly pre-activated.
- Reused the existing raw runtime binding for untyped stop events so specialist
  liveness returns to idle without guessing.
- Recorded `reported_agent_type` and `binding_source` whenever Kanban must bind
  an untyped runtime, while leaving ambiguous candidates unowned.
- Required the exact Codex custom-agent type at spawn time so the intended TOML
  instructions, permissions, model settings, and runtime identity are loaded.
- Defined `task_name` as a task/thread label rather than an agent-type selector
  and made missing exact-type support a visible delegation limitation.

AI disclosure:

This release was developed, reviewed, audited, and prepared by the main AI
Agent Manager using the exact model `gpt-5.6-sol` (GPT-5.6 Sol). No delegated
agent was used for this release because the active `spawn_agent` surface did
not expose an exact custom-agent selector; substituting its `default` agent
would not load the required specialist TOML. The work was coordinated with
Codex Kanban checkouts `2a6ae21` for intake and implementation and `7249fa4`
for release integration and preparation.

## 0.1.12 - 2026-07-11

This release makes agent model selection follow the active Codex turn and
replaces stale runtime-agent People rows with a role-based realtime overview.
It also starts main-agent liveness at prompt intake, associates active work
when it can be inferred safely, and strengthens exact release disclosures.

Public commits:

- `b18d641` removes pinned model names from packaged agent profiles so spawned
  agents inherit the calling Codex turn's model, and records the authoritative
  model, session, and turn identifiers from hook payloads.
- `a19691f` groups fresh runtime instantiations under stable board-scoped agent
  roles, shows per-instance state/model details, and removes finished or stale
  instances from the live People overview without losing Activity history.
- `944534c` requires versioned model slugs/named variants, agent-role
  attribution, and an exact Codex Kanban coordination commit SHA in release AI
  disclosures, and tightens the verified 0.1.11 disclosure.
- `64f3331` merges CK-0665, CK-0666, and CK-0669 into `release/0.1.12`.
- `2a99360` installs prompt-start lifecycle handling, makes the main agent and
  delegated agents visible while they work, displays their active card and
  exact model when available, and documents dynamic subagent model choice.
- `580fe7e` merges the realtime People lifecycle follow-up into the reopened
  `release/0.1.12` branch.

Release metadata note:

The release metadata commit that updates this changelog and bumps package
version files is not self-referenced; this follows the existing changelog
convention for avoiding unstable self-hashes.

Changes:

- Made packaged role profiles model-agnostic so each spawned agent inherits
  the model active for the Codex turn that starts it.
- Recorded exact per-turn runtime model, session, and turn identifiers from
  Codex hook payloads and surfaced model/turn information in Activity.
- Kept People entries stable at the configured role level while nesting all
  fresh concurrent instantiations with their status, card, scope, and model.
- Removed finished instantiations immediately and aged abandoned running,
  waiting, or idle instantiations out after the configured stale interval.
- Added the missing `UserPromptSubmit` hook so the main agent becomes running
  as soon as a prompt is submitted and returns to idle when its turn stops.
- Associated a uniquely active assigned card with a live agent while avoiding
  ambiguous card inference, and showed each live instance's exact model.
- Kept model inheritance as the subagent default while allowing the main agent
  to choose a supported lighter model for bounded, low-risk delegated work.
- Required exact, evidence-backed AI model and Codex Kanban coordination
  hashes in future release disclosures.

AI disclosure:

This release was developed, reviewed, audited, and prepared with AI assistance
using the exact model `gpt-5.6` (GPT-5.6 Sol). It was used by the main AI Agent
Manager, with implementation recorded under the Project Implementer role, and
by delegated Project Architect, Test Strategist, and Project Release Manager
agents. Their exact Codex Kanban coordination checkouts were `095e5fd` for the
initial main and architecture work, `a19691f` for the original release audit,
`3c6a003` for the realtime lifecycle test review, `2a99360` for the post-fix
release audit, and `580fe7e` for the reopened final audit and preparation.

## 0.1.11 - 2026-07-04

This release improves Activity handling, event retention, branch guidance,
code standards, release-branch file-size compliance, static app module
organization, snapshot CLI inspection, and concurrent local SQLite
coordination.

Public commits:

- `473deec` prunes SQLite event rows older than the retention window during
  graceful server shutdown.
- `e02dc50` prints the number of pruned event rows during shutdown cleanup.
- `071ba50` changes the Activity panel to load the latest 10 events first and
  fetch older events in pages of 10 while scrolling inside the panel.
- `1d805e5` fixes Activity panel scrolling and row wrapping so event text stays
  readable in narrow layouts.
- `b401d68` links Activity events to related cards, opens archived cards on
  demand, and shows a picker when an event references multiple cards.
- `8991af8` clarifies that same-topic local follow-up work may stay on the
  existing card branch instead of forcing redundant sibling branches.
- `aef48a5` merges the `CK-0346` event retention work into `release/0.1.11`.
- `e1cffad` merges the `CK-0349` branch-policy update into `release/0.1.11`.
- `e6819c4` merges the `CK-0347` Activity pagination work into
  `release/0.1.11`.
- `bfd6c4f` merges and optimizes the `CK-0348` Activity card-link work with the
  paginated Activity implementation.
- `e4dc550` adds explicit release-branch code standards for file size,
  responsibility splits, naming, and behavior-preserving cleanup.
- `248a8a5` enables concurrent SQLite store access with async-capable store
  entrypoints, WAL/busy-timeout connection settings, and concurrency tests.
- `8e365b8` merges the `CK-0354` async SQLite store work into
  `release/0.1.11`.
- `619326a` refactors oversized release-branch frontend and test files into
  responsibility-focused modules so tracked code assets stay below the hard
  1000-line cap.
- `6c3e236` moves browser app JavaScript assets into a Vue-inspired
  `static/app/` folder with lowercase/kebab-case browser script filenames and
  updates script/test references.
- `6f02591` merges the `CK-0358` static app module move into
  `release/0.1.11`.
- `bd92d1a` fixes release CI JavaScript syntax paths for the moved static app
  files and includes dashboard static assets in built wheels.
- `dc9e8ca` adds a regression test that keeps dashboard script paths and CI
  JavaScript syntax targets aligned.
- `a3198f7` adds `snapshot --done-limit` to the project CLI so agents can
  inspect completed-card history without querying SQLite directly.
- `40ed5e0` merges the `CK-0368` snapshot done-limit CLI fix into
  `release/0.1.11`.

Release metadata note:

The release metadata commit that updates this changelog and bumps package
version files is not self-referenced; this follows the existing changelog
convention for avoiding unstable self-hashes.

Changes:

- Kept only recent Activity events in the initial snapshot and added a paged
  `/api/events` flow for loading older events without growing the side rail
  unexpectedly.
- Made Activity events clickable when they reference cards, including events
  tied to archived cards and events that need a multi-card picker.
- Centralized Activity event related-card enrichment so both initial snapshots
  and older event pages expose the same clickable card metadata.
- Added shutdown cleanup for local coordination events older than 48 hours and
  a terminal summary of how many rows were pruned.
- Updated project and packaged skill guidance so related follow-up requests
  from the same local user can reuse an existing same-topic feature branch when
  that reduces redundant code and merge conflicts.
- Added a release-branch `Code Standards` instruction covering file-size
  limits, domain-responsibility splits, avoiding generic `mixin` names for
  split-out code, and removing unnecessary code without accidental behavior
  changes.
- Improved local SQLite coordination for concurrent agents, CLI commands, and
  server handlers by removing the process-local store serialization point,
  adding async-capable store wrappers, and strengthening SQLite busy/WAL
  connection settings.
- Split oversized release-branch frontend and test modules by responsibility
  so every tracked Python, JavaScript, CSS, and HTML code asset stays below the
  hard 1000-line limit.
- Organized browser app JavaScript under `kanban_server/static/app/` with
  lowercase/kebab-case browser script filenames, including the dashboard
  entrypoint at `/static/app/main.js`.
- Fixed release CI and package metadata so the moved static app scripts are
  checked in CI and included in built wheels.
- Added `--done-limit` to the `snapshot` project CLI command with
  overview-compatible `0`, `N`, and `-1` semantics for completed-card history.

AI disclosure:

This release was developed, reviewed, and prepared with help from AI agents
using the exact model `gpt-5.6` (GPT-5.6 Sol) for the main coordinating agent and its
delegated implementation, review, and release agents. The work was coordinated
with Codex Kanban commit
`83fb4ca`, the verified release immediately preceding 0.1.11.

## 0.1.10 - 2026-07-04

This release strengthens continuous development coordination by separating
independent contributors into auditable branches and making delegated findings
durable on parent cards.

Public commits:

- `116c4ff` tightens branch, contributor, rebase, and human-review guidance for
  feature/fix cards, and updates conflict detection so shared release targets
  require distinct feature branches.
- `9dd609b` merges the `CK-0334` branch workflow card into `release/0.1.10`.
- `cac7470` adds a supported `card-comment` project CLI command, parent-card
  comment guidance for delegated results, hook context for subagents, and
  focused CLI/comment tests.
- `558202e` merges the refreshed `CK-0338` card-comment workflow into
  `release/0.1.10`.

Release metadata note:

The release metadata commit that updates this changelog and bumps package
version files is not self-referenced; this follows the existing changelog
convention for avoiding unstable self-hashes.

Changes:

- Documented that separate user requests, implementation scopes, and AI agents
  should be treated as separate contributors with card-specific feature/fix
  branches, commits, human review before release-branch merge, and refreshes
  from the updated release branch.
- Added `card-comment` to the project CLI so agents have a supported way to add
  durable notes to cards without relying on indirect event ingestion.
- Clarified that subagent and contributor completion results belong as concise
  comments on the parent coordination card, while child cards keep local
  execution state such as checks, branches, and handoff SHAs.
- Updated project guidance, the packaged Kanban skill, generated project
  prompt text, subagent hook context, public release guidance, and regression
  tests for the new coordination workflow.

AI disclosure:

This release was developed, reviewed, and prepared with help from AI agents
using GPT-5 and GPT-5.5, coordinated through the Codex Kanban workflow.

## 0.1.9 - 2026-07-02

This release makes Kanban startup and delegation guidance harder to misapply in
fresh Codex sessions.

Public commit:

- `6a9b33c` makes CLI examples derive and validate the `codex_kanban`
  checkout before setting `PYTHONPATH`, and changes Kanban guidance into a
  standing instruction to choose relevant specialized subagents when they can
  improve software quality, usability, safety, maintainability, or data
  integrity.

Release metadata note:

The release metadata commit that updates this changelog and bumps package
version files is not self-referenced; this follows the existing changelog
convention for avoiding unstable self-hashes.

Changes:

- Added `KANBAN_REPO` guidance so agents do not copy stale absolute checkout
  paths when running the Kanban project CLI from another repository.
- Updated the skill, root instructions, docs, and generated project prompt so
  Codex Kanban is a standing instruction to consider all available
  board-scoped specialists, including project-local profiles, without spawning
  every profile by default.
- Added prompt regression coverage for the safer import path and standing
  delegation wording.

AI disclosure:

This release was developed, reviewed, and prepared with help from AI agents
using GPT-5.5, coordinated through the Codex Kanban workflow.

## 0.1.8 - 2026-07-02

This release tightens agent startup coordination, reduces first-overview noise,
and keeps board people fields in sync with current AI agent profiles.

Public commits:

- `d95c3a9` adds `--done-limit` to the startup overview so active cards remain
  visible while completed-card history is capped by default, and documents the
  current explicit-subagent-request limitation.
- `5a1d792` clarifies that multi-intent human requests should become separate
  sibling cards or parent/child cards before implementation starts.
- `aeca785` refreshes board-scoped AI participants during startup overview,
  hook/session startup, and UI snapshot loading so current generic/default and
  project-local agents appear in people, owner, assignee, and comment-writer
  fields.

Release metadata note:

The release metadata commit that updates this changelog and bumps package
version files is not self-referenced; this follows the existing changelog
convention for avoiding unstable self-hashes.

Changes:

- Limited done cards in first overview output while preserving all non-done
  work categories and hidden-count hints.
- Added guidance and generated prompt text to split independent features, fixes,
  apps, roles, UI flows, or deployment scopes into separate cards.
- Refreshed board participants from current default/generic agent definitions,
  installed Codex agent files, registered project profiles, and project-local
  `.codex/agents` on startup/reload.
- Preserved and seeded the board-scoped AI agent manager alongside
  profile-backed agents.

AI disclosure:

This release was developed with help from AI agents using GPT-5.5, coordinated
through the Codex Kanban workflow.

## 0.1.7 - 2026-07-02

This release simplifies the documented release integration gate so CI runs once
on the exact merge commit that will advance `main`.

Public commit:

- `a48a7dc` clarifies that agents should create the
  no-fast-forward release merge commit before the first public push for a
  release, push that merge SHA to `release/<version>`, wait for CI there, and
  only then fast-forward `main`.

Release metadata note:

The release metadata commit that updates this changelog and bumps package
version files is not self-referenced; this follows the existing changelog
convention for avoiding unstable self-hashes.

Changes:

- Avoided the earlier two-run pattern of testing the pre-merge release tip and
  then testing the release merge commit.
- Documented a no-`gh` CI polling option using `curl` and Python's standard
  library, while keeping GitHub's web UI as a valid manual check.
- Kept the visible release branch and explicit merge commit history shape from
  0.1.6.

AI disclosure:

This release was developed with help from AI agents using GPT-5.5, coordinated
through the Codex Kanban workflow.

## 0.1.6 - 2026-07-02

This release documents and validates a clearer release-branch integration flow
for continuous development and CI transparency.

Public commit:

- `c80d03a` updates project release rules, the bundled Codex Kanban skill, and
  public release docs so feature/fix commits remain grouped on
  `release/<version>` and `main` advances through an explicit release merge
  commit that has passed release-branch CI.

Release metadata note:

The release metadata commit that updates this changelog and bumps package
version files is not self-referenced; this follows the existing changelog
convention for avoiding unstable self-hashes.

Changes:

- Required public releases to create a no-fast-forward release merge commit
  whose first parent is the previous `main` and whose second parent is the
  release branch tip.
- Required the release merge commit to be pushed back to `release/<version>`
  and pass CI before `main` fast-forwards to the same SHA.
- Clarified allowed public refs: explicit release branches, the approved
  `main` release-merge fast-forward ref, and release tags.
- Added the release integration flow to the main Codex Kanban docs and public
  release checklist.

AI disclosure:

This release was developed with help from AI agents using GPT-5.5, coordinated
through the Codex Kanban workflow.

## 0.1.5 - 2026-07-02

This release sharpens ecosystem coordination, reduces agent startup context
load, adds a GitHub-facing README, and aligns bundled agent profiles with
GPT-5.5.

Public commits:

- `17dc122` adds ecosystem affected-path/deployment-disposition tracking,
  mirrors delegated-agent feedback into card comments, and tightens card
  description guidance so later feedback becomes comments or child cards.
- `8104cbb` adds the lean `overview` API/CLI startup contract, archive-aware
  card listing, shared single-repo auto-registration helpers, and card UI
  improvements for descriptions and ecosystem affected paths.
- `dcca303` adds the missing default abstract agent TOMLs and pins all bundled
  agent profiles to GPT-5.5.

Release metadata note:

The release metadata commit that updates this changelog, README, and package
version files is not self-referenced; this follows the existing changelog
convention for avoiding unstable self-hashes.

Changes:

- Added `GET /api/overview` and `python3 -m kanban_server.project overview`
  so agents can resolve the current repo or ecosystem before reading active
  non-archived cards.
- Added CLI archive parity for snapshots and explicit archived-card hints in
  overview output.
- Added durable deployment dispositions and affected registered project paths
  so ecosystem release/deploy work can record every affected app, repo, or
  worktree.
- Mirrored delegated-agent feedback events into card comments for card owners.
- Improved the card dialog with a taller description field, compact visible
  fields, and secondary coordination fields behind a `More fields` toggle.
- Displayed affected ecosystem path chips directly on cards.
- Added GPT-5.5 TOML definitions for all default abstract agent profiles.
- Added this GitHub README and refreshed docs for overview-first startup.

AI disclosure:

This release was developed with help from AI agents using GPT-5.5, coordinated
through the Codex Kanban workflow.

## 0.1.4 - 2026-07-01

This release makes dashboard startup failures more human-friendly when the
requested host/port is already in use.

Public commit:

- `2872c51` handles dashboard port conflicts gracefully by printing a concise
  Codex Kanban error, including a `kill <pid>` hint when one matching listener
  process can be identified, preserving tracebacks for unrelated startup
  errors, and adding regression coverage for ambiguous same-port and dual-stack
  listener cases.

Release metadata note:

The release metadata commit that updates this changelog and bumps package
version files is not self-referenced; this follows the existing changelog
convention for avoiding unstable self-hashes.

Changes:

- Replaced the raw Python traceback for occupied dashboard ports with an
  actionable message that names the host/port and suggests either stopping the
  existing process or choosing another port.
- Added Linux `/proc`-based listener PID detection so the message can include a
  concrete `kill <pid>` command when the matching listener is unambiguous.
- Kept PID hints conservative for ambiguous listeners and covered same-port
  different-address plus dual-stack IPv6 wildcard cases.
- Added focused tests and smoke coverage for the startup error path.

AI disclosure:

This release was developed with help from AI agents using GPT-5, coordinated
through the Codex Kanban workflow.

## 0.1.3 - 2026-07-01

This release strengthens release intake guardrails, adds main-agent-first
request intake metadata, and shows the running dashboard build version/hash.

Public commits:

- `1d2f6f9` hardens release-intake guidance so release work audits included and
  excluded cards/branches before main is advanced.
- `8655a9e` requires release-intake audit delegation when a suitable
  read-only release agent is available.
- `c71912a` adds structured main-agent intake metadata, optional dashboard
  intake fields, a runtime dashboard version/hash tag, and focused regression
  coverage.

Release metadata note:

The release metadata commit that updates this changelog and bumps package
version files is not self-referenced; this follows the existing changelog
convention for avoiding unstable self-hashes.

Changes:

- Added optional card intake fields for request type, source, reporter, impact,
  evidence, and affected paths so human feature requests and error reports can
  move from the main AI agent into durable cards.
- Kept direct dashboard card entry optional while making main-agent CLI-created
  cards default to `intake_source=main_agent`.
- Added compact dashboard build metadata showing package version, git hash, and
  dirty-tree state from runtime snapshot metadata.
- Updated Codex Kanban skill/docs to describe main-agent-first request intake
  and release inclusion/exclusion audit expectations.
- Added store, CLI, HTTP, static asset, and snapshot regression tests covering
  the new intake and build metadata paths.

AI disclosure:

This release was developed with help from AI agents using GPT-5, coordinated
through the Codex Kanban workflow.

## 0.1.2 - 2026-06-30

This release improves dashboard cleanup, CLI handoff hygiene, and AI-agent
coordination for Codex Kanban projects.

Public commit:

- `aa05ba8` improves warning-card archiving, CLI blocker clearing, default AI
  manager attribution for CLI-created cards, and Codex Kanban delegation
  guidance.

Release metadata note:

The release metadata commit that updates this changelog and bumps package
version files is not self-referenced; this follows the 0.1.1 changelog
convention for avoiding unstable self-hashes.

Changes:

- Fixed dashboard archiving so cards with coordination or dependency warnings
  can still be archived, and bulk archive continues when one selected card
  fails.
- Added `card-move --clear-blocker` and support for `--blocker ""` so agents
  can clear stale blocker text without raw API PATCH calls.
- Made CLI-created cards with `--board` default to a board-scoped
  `AI Agent Manager` actor instead of the local human developer identity.
- Clarified Codex Kanban subagent delegation guidance in the skill, docs, hook
  context, and project prompt text.
- Added regression tests for warning-card archiving, blocker clearing, and
  default CLI card creator attribution.

AI disclosure:

This release was developed with help from AI agents using GPT-5, coordinated
through the Codex Kanban workflow.

## 0.1.1 - 2026-06-29

This release prepares the Codex Kanban dashboard for coordinated AI-assisted
development, release hygiene, and public repository publication.

Public history note:

The unpublished release branch was rewritten before publication so public Git
history does not retain personal author metadata, local machine paths, local
tool refs, or private infrastructure references. Local-only working commits
from before that cleanup are intentionally not part of the public history.

Public commit:

- `a675f6c` imports the sanitized 0.1.1 public tree.

Changes:

- Added AGPLv3-only licensing and package metadata.
- Added release changelog rules, public-release guidance, and local-state
  ignore rules.
- Added clonable Codex Kanban skill and agent definitions under `.codex/`.
- Added Black, Ruff, Pyright, JavaScript syntax, compile, unittest, and
  ResourceWarning checks to development and CI workflows.
- Refactored store and project code into responsibility-focused packages under
  the model-view-controller project rules.
- Fixed dashboard startup, frontend script scope collisions, board migration,
  snapshot scaling, card ownership display, and chronological card ordering.
- Rewrote the unpublished release history into a sanitized public branch.
- `b4c5fcb` updated GitHub Actions dependencies to Node 24-compatible releases
  so CI runs without the Node.js 20 deprecation warning.

AI disclosure:

This release was developed with help from AI agents using GPT-5.5, coordinated
through the Codex Kanban workflow.

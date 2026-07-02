# Changelog

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

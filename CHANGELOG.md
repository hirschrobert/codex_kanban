# Changelog

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

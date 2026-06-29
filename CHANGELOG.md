# Changelog

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

AI disclosure:

This release was developed with help from AI agents using GPT-5.5, coordinated
through the Codex Kanban workflow.

# Project Context: Codex Kanban

This repository contains a generic Codex-native Kanban dashboard for coordinating
human developers, the main AI agent, and optional AI subagents.

## Codex Kanban

- Use the `codex-kanban` skill for concrete feature, fix, docs, test, review,
  release, registration, or multi-agent work. Skip Kanban for trivial command
  checks and keep exploratory discussion read-only until implementation is
  approved.
- For concrete multi-agent work, create one parent coordination card plus one
  linked child for the main implementer and each delegated subagent doing
  material work. Assign children to board-scoped participants and record
  start/finish/handoff on those child cards.
- For ecosystem release/deploy work, record affected apps, repos, worktrees,
  and deployment dispositions before marking production deployment complete.
- Keep this app abstract. Do not hardcode project-specific domains, agent names,
  release trains, accounting rules, or deployment policy into the dashboard.
- Concrete project rules belong in each project repository's `AGENTS.md` and,
  when needed, project-local `.codex/agents/`.
- The SQLite database is local coordination state. Do not treat it as production
  application data.

## Development Rules

- Prefer the existing standard-library Python implementation unless a task
  explicitly requires a new dependency.
- Follow a model-view-controller structure: keep persistent data and domain
  rules in model/store modules, HTTP/CLI/user action orchestration in controller
  modules, and dashboard rendering/static presentation in view modules.
- Code files SHOULD stay around 600 lines of code and MUST NOT exceed 1000
  lines of code. Split files by responsibility before they cross the hard
  ceiling.
- Treat Black and Ruff findings as design feedback, not just warnings to
  silence. Prefer cohesive packages, single-responsibility modules, shared
  helpers, and explicit public APIs over duplicated code, compatibility glue, or
  repeated re-export workarounds.
- Keep package folders organized by responsibility. Public package
  `__init__.py` files may expose stable imports, but implementation modules
  should import concrete sibling modules directly instead of reaching through
  aggregate public APIs.
- Keep dashboard UI, server, store, hooks, and project-registration behavior
  loosely coupled and generic.
- Add focused tests for store behavior, registration behavior, and API changes.
- Run relevant checks before handoff, at minimum the focused Python tests for
  changed backend/store behavior and `node --check` for changed frontend JS.

## Release Rules

- Every release must update `CHANGELOG.md` with a concise description of the
  user-visible changes and the short commit hashes included in the release.
- Every release changelog entry must disclose AI assistance and name the AI
  model used by the release agents. For the 0.1.1 release, state that the
  release was developed with help from AI agents using GPT-5.5.
- Before pushing a public release, audit tracked files and the intended push
  refs for personal data, local machine paths, local databases, secrets, and
  generated coordination state.
- Public pushes must target only explicit release branches, the approved
  `main` release-merge fast-forward ref, or release tags. Do not mirror every
  local ref from a development repository.
- The full CI workflow runs on release branches, not on main pushes. Keep
  feature, fix, and release metadata commits on `release/<version>`, then
  integrate them with an explicit no-fast-forward release merge commit whose
  first parent is the previous `main` and whose second parent is the release
  branch tip. Push that merge commit back to `release/<version>` and wait for
  CI on that exact SHA before advancing `main`.
- Advance `main` only by fast-forwarding it to the exact release merge commit
  SHA that passed CI on `release/**`; do not squash, rebase, rewrite, or create
  an untested main-only commit.
- Rewriting author metadata, signatures, or local refs is destructive release
  preparation and requires explicit human approval plus the intended public
  author/signing identity.

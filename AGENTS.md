# Project Context: Codex Kanban

This repository contains a generic Codex-native Kanban dashboard for coordinating
human developers, the main AI agent, and optional AI subagents.

## Codex Kanban

- Use the `codex-kanban` skill for concrete feature, fix, docs, test, review,
  release, registration, or multi-agent work. Skip Kanban for trivial command
  checks and keep exploratory discussion read-only until implementation is
  approved.
- Startup overview and explicit `codex-kanban` reloads must refresh
  board-scoped AI participants from the current generic/default profiles and
  discoverable project-local profiles so UI people fields stay current.
- Split multi-intent human requests before implementation starts. If one prompt
  contains independent features, fixes, affected apps/repos, user roles, UI
  flows, or deployment scopes, create separate sibling cards or a coordination
  parent with child cards instead of one bundled implementation card.
- Treat Codex Kanban as a standing project instruction for the first/main AI
  agent to actively consider specialized subagents at session start and before
  each material implementation, review, release, documentation, or audit step.
  Use them more consequently when they can improve software quality, usability,
  safety, maintainability, or data integrity. Do not spawn every available
  profile by default; choose the smallest relevant set from the board-scoped
  participants and explain the delegation reason or why delegation was skipped.
- For concrete multi-agent work, create one parent coordination card plus one
  linked child for the main implementer and each delegated subagent doing
  material work. Assign children to board-scoped participants and record
  start/finish/handoff on those child cards. If the active Codex environment
  still disallows spawning, record the cards and surface the blocker instead of
  silently folding delegated work into the parent agent.
- Treat different user requests, implementation scopes, and agents as separate
  contributors in the cards, but do not force a new branch when the human's
  local follow-up request continues the same object, UI surface, domain concept,
  or cohesive topic on an unmerged feature/fix branch for the same release.
  In that case, continue on the existing topic branch, create or update a
  related child/sibling card that records the shared branch, and add focused
  commits for the new card. Create a new `feature/<CARD-ID>-...` or
  `fix/<CARD-ID>-...` branch when the work is unrelated, independently
  reviewable, from a different release/deployment scope, or would make the
  current topic branch too broad. Never combine unrelated cards on one branch or
  leave unstaged implementation changes as handoff state. Coordination, review,
  release, and read-only audit cards do not need their own write branch, but
  they must record which implementation branch or release branch they inspect.
- Merge a feature/fix branch into the upcoming release branch only after human
  final review/approval. After any branch lands on the release branch, all other
  active feature/fix branches must rebase or otherwise refresh from that release
  branch and record updated SHAs/checks before continuing.
- When a subagent or other contributor finishes material work, write its result
  as a concise comment on the parent coordination card. Child cards hold
  execution status, branch/check details, and local handoff facts; parent-card
  comments hold the durable findings, decisions, blockers, and next steps for
  continuing the topic.
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
  feature and fix work on explicit topic/card branches until human-approved merge
  to `release/<version>`. Keep release metadata commits on `release/<version>`,
  then create an explicit no-fast-forward release merge commit before the first
  public push for that release. The merge commit's first parent is the previous
  `main` and its second parent is the release branch tip. Push that merge commit
  to `release/<version>` once and wait for CI on that exact SHA before advancing
  `main`.
- Advance `main` only by fast-forwarding it to the exact release merge commit
  SHA that passed CI on `release/**`; do not squash, rebase, rewrite, or create
  an untested main-only commit.
- Rewriting author metadata, signatures, or local refs is destructive release
  preparation and requires explicit human approval plus the intended public
  author/signing identity.

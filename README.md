# Codex Kanban

Codex Kanban is a local, Codex-native realtime Kanban dashboard for coordinating
human developers, the main AI agent, and optional specialist subagents.

It stores coordination state in SQLite, serves a small browser dashboard, and
ships reusable Codex skill and agent definitions under `.codex/`.

## Highlights

- Project-scoped boards with board-scoped human and AI participants.
- Durable cards for feature requests, fixes, reviews, releases, and handoffs.
- Lean startup overview for agents that resolves the current repo or ecosystem
  before listing active cards.
- Ecosystem-aware affected app/repo/worktree metadata and deployment
  dispositions.
- Card comments for human notes and delegated-agent feedback.
- Dependency links, recurring workflow cards, archive support, and release
  guardrails.
- Generic GPT-5.5 agent profile TOMLs for implementation, review, release,
  audit, architecture, API contract, domain model, and test strategy work.

## Quick Start

```bash
python3 -m kanban_server --host 127.0.0.1 --port 8766
```

Then open:

```text
http://127.0.0.1:8766
```

For local development:

```bash
uv sync --dev
uv run python -m unittest discover -s tests
```

## Documentation

- Main user and agent guide: [docs/codex-kanban.md](docs/codex-kanban.md)
- Public release checklist: [docs/public-release.md](docs/public-release.md)
- Release history: [CHANGELOG.md](CHANGELOG.md)

## License

Codex Kanban is licensed under the GNU Affero General Public License v3.0 only.
See [LICENSE](LICENSE).

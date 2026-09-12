# Codex Kanban Deployment

This guide deploys two related but separate components:

1. the local dashboard server and command-line entry points;
2. the Codex skill, custom-agent profiles, and lifecycle hooks.

The supported deployment source is a checked-out, reviewed Git revision. The
Python wheel contains the server and static dashboard; Codex assets remain in
the checkout because user configuration must be merged without overwriting
unrelated settings.

Commands below assume Linux, systemd user services, `git`, and `uv`. Production
service changes, restarts, database replacement, package publication, and Git
release operations still require the approvals defined by the current
repository.

## Paths

The examples use:

```bash
KANBAN_REPO="$HOME/.local/share/codex-kanban-src"
KANBAN_STATE="$HOME/.codex/codex-kanban"
```

`KANBAN_REPO` is the reviewed source checkout. `KANBAN_STATE` contains the
default SQLite database. Do not place the database in the Git checkout.

The tracked [systemd user-service template](../assets/codex-kanban.service)
expects the `codex-kanban` executable at `$HOME/.local/bin/codex-kanban`, which
is the normal `uv tool` binary location.

## First Installation

Clone the repository and select the reviewed release tag or commit:

```bash
git clone https://github.com/hirschrobert/codex_kanban.git "$KANBAN_REPO"
git -C "$KANBAN_REPO" switch --detach <reviewed-tag-or-commit>
```

Run the checks before installing:

```bash
cd "$KANBAN_REPO"
uv sync --frozen
uv run python -m unittest discover -s tests
```

Install the dashboard commands from that exact checkout:

```bash
uv tool install --force "$KANBAN_REPO"
test -x "$HOME/.local/bin/codex-kanban"
```

Install or update the Codex skill and the managed agent-profile files:

```bash
python3 "$KANBAN_REPO/scripts/install_codex_assets.py"
```

The installer validates skill-local Markdown references, replaces the managed
`codex-kanban` skill directory as one unit, preserves unrelated custom agents,
and backs up replaced assets under `$CODEX_HOME/backups/` or
`$HOME/.codex/backups/`. It deliberately does not rewrite the user's
`config.toml`; review `$KANBAN_REPO/.codex/config.toml` and merge only the
desired settings.

Install the service template and start it only after reviewing its contents:

```bash
install -d -m 0700 "$KANBAN_STATE" "$HOME/.config/systemd/user"
install -m 0644 \
  "$KANBAN_REPO/.codex/skills/codex-kanban/assets/codex-kanban.service" \
  "$HOME/.config/systemd/user/codex-kanban.service"
systemctl --user daemon-reload
systemctl --user enable --now codex-kanban.service
```

For a nonstandard `uv tool` binary directory, create a systemd drop-in and
replace `ExecStart` with the absolute installed executable path:

```ini
[Service]
ExecStart=
ExecStart=/absolute/path/to/codex-kanban --host 127.0.0.1 --port 8766
```

Install or refresh the Codex lifecycle hooks from the same checkout:

```bash
PYTHONPATH="$KANBAN_REPO" python3 -m kanban_server.hook install \
  --repo "$KANBAN_REPO" \
  --server-url "http://127.0.0.1:8766"
```

Review and trust the hook when Codex asks. Start a new Codex session after
skill, profile, configuration, or hook changes; an existing session does not
reload all of those assets dynamically.

## Verification

Verify the service and API:

```bash
systemctl --user status codex-kanban.service --no-pager
curl --fail --silent --show-error \
  http://127.0.0.1:8766/api/projects >/dev/null
```

Verify the installed skill is complete:

```bash
test -f "$HOME/.codex/skills/codex-kanban/SKILL.md"
test -f "$HOME/.codex/skills/codex-kanban/docs/codex-kanban.md"
test -f "$HOME/.codex/skills/codex-kanban/docs/deployment.md"
python3 "$KANBAN_REPO/scripts/install_codex_assets.py" --dry-run
```

If `CODEX_HOME` is set, substitute that directory for `$HOME/.codex` in manual
checks. Finally, run the startup overview from a new Codex session and confirm
the expected project and board-scoped People entries appear.

## Updating

Before changing a running deployment, identify the currently installed Git
revision and take a recoverable database backup. Stop/restart commands are
service mutations and require the applicable approval:

```bash
git -C "$KANBAN_REPO" rev-parse HEAD
systemctl --user stop codex-kanban.service
backup_file="$KANBAN_STATE/kanban.sqlite3.$(date -u +%Y%m%dT%H%M%SZ).bak"
cp --preserve=mode,timestamps "$KANBAN_STATE/kanban.sqlite3" "$backup_file"
```

Select and verify the new reviewed revision, then update both deployment
components from the same checkout:

```bash
git -C "$KANBAN_REPO" fetch --tags origin
git -C "$KANBAN_REPO" switch --detach <new-reviewed-tag-or-commit>
cd "$KANBAN_REPO"
uv sync --frozen
uv run python -m unittest discover -s tests
uv tool install --force "$KANBAN_REPO"
python3 "$KANBAN_REPO/scripts/install_codex_assets.py"
```

Refresh the tracked service and hooks, then restart and verify:

```bash
install -m 0644 \
  "$KANBAN_REPO/.codex/skills/codex-kanban/assets/codex-kanban.service" \
  "$HOME/.config/systemd/user/codex-kanban.service"
PYTHONPATH="$KANBAN_REPO" python3 -m kanban_server.hook install \
  --repo "$KANBAN_REPO" \
  --server-url "http://127.0.0.1:8766"
systemctl --user daemon-reload
systemctl --user restart codex-kanban.service
curl --fail --silent --show-error \
  http://127.0.0.1:8766/api/projects >/dev/null
```

Start a new Codex session after the asset update.

## Rollback

Switch the checkout back to the recorded prior revision, rerun its tests, and
install both the server and Codex assets from that same revision:

```bash
git -C "$KANBAN_REPO" switch --detach <previous-reviewed-tag-or-commit>
cd "$KANBAN_REPO"
uv sync --frozen
uv run python -m unittest discover -s tests
uv tool install --force "$KANBAN_REPO"
python3 "$KANBAN_REPO/scripts/install_codex_assets.py"
```

If the newer revision changed the database incompatibly, stop the service and
restore the matching pre-update database backup before restarting. Do not copy
a live SQLite database over the active file.

Refresh the prior service template and hooks, restart the service, repeat the
verification checks, and start a new Codex session. Asset backups created by
the installer can also restore the exact prior skill and managed profile files.

## Troubleshooting

Inspect service logs without changing state:

```bash
journalctl --user -u codex-kanban.service --since today --no-pager
```

Common failures:

- `ModuleNotFoundError: kanban_server`: reinstall the reviewed checkout with
  `uv tool install --force` and verify the service's executable path.
- Missing skill references: rerun the asset installer and confirm the files
  under `skills/codex-kanban/docs/` exist in the selected source revision.
- Hooks use an old checkout: rerun the hook installer with the intended
  `--repo` path and start a new Codex session.
- The port is busy: identify the existing listener before changing the port;
  keep the service, hook URL, and `CODEX_KANBAN_URL` consistent.

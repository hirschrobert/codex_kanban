# Codex Project Assets

This directory contains clonable Codex assets for this repository.

- `agents/` contains generic AI agent profiles used by the Kanban workflow.
- `config.toml` supplies Standard speed and a Sol/high subagent fallback without
  choosing the main model.
- `skills/codex-kanban/` contains the Codex Kanban skill and its interface
  metadata.

Read [model routing](skills/codex-kanban/model-routing.md) before delegation.
General profiles leave model and effort selectable by the parent; the security
specialist pins Daybreak Blue/xhigh. All profiles explicitly use Standard speed.

For use from other repositories, copy the profiles to `~/.codex/agents/` and the
whole skill directory to `~/.codex/skills/codex-kanban/`. Merge the two `[agents]`
defaults from `config.toml` into your user configuration, preserving existing
settings. Keep `service_tier = "default"` for Standard speed. Do not replace the
entire user configuration. The project configuration applies in trusted
checkouts; user defaults cover other projects and built-in subagents too.

Start a new Codex session to load changed custom agents, then run the Kanban
startup overview to refresh board participants. Refreshing People does not
reload an already-running agent's model configuration. Daybreak requires access
in the active account/client; see the routing guide for the explicit fallback.

Security policy can remain repository-local and ignored by Git. The reviewer
considers applicable `SECURITY.md` files regardless of tracking, plus explicitly
referenced local security documents. Use `.git/info/exclude` for a local-only
exclusion and follow the routing guide's confidentiality rules for handoffs.

Local Codex state, databases, logs, and machine-specific configuration should
remain outside the repository or in ignored `.local` files.

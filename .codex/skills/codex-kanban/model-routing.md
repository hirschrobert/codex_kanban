# Agent Model Routing

Choose the model and reasoning effort before spawning a contributor. These are
default recommendations for bounded roles, not instructions to spawn every
role. Respect the active client's available models, effort levels, and spawn
controls. Model access is account-specific; the dashboard does not select or
enforce model settings.

## Defaults

The repository's `.codex/config.toml` sets `agents.default_subagent_model` to
`gpt-5.6-sol` and `agents.default_subagent_reasoning_effort` to `high`. Merge
these defaults into the user's Codex configuration when installing the assets
for use across repositories. The main model stays independently selectable.

All packaged profiles set `service_tier = "default"` for Standard speed, even
if the parent uses Fast. Keep Standard speed for built-in contributors too;
check the effective session configuration when the spawn surface cannot select
a tier. Do not enable Fast merely to compensate for higher reasoning effort.

General profiles omit both `model` and `model_reasoning_effort` so explicit
spawn choices can override the cheaper subagent fallback. Supply both fields
when the spawn surface supports them. Without an explicit choice, these roles
use the configured Sol/high fallback. If neither subagent defaults nor explicit
selection is available, Codex inherits the parent: disclose that limitation
before fanning out expensive work instead of claiming the cost policy applied.

| Role | Requested model | Requested effort |
| --- | --- | --- |
| `project_architect` | `gpt-5.6-sol` | `xhigh` |
| `project_reviewer` | `gpt-5.6-sol` | `xhigh` |
| `domain_model_steward` | `gpt-5.6-sol` | `xhigh` |
| `api_contract_steward` | `gpt-5.6-sol` | `high` |
| `project_implementer` | `gpt-5.6-terra` | `high` |
| `architecture_impact_analyst` | `gpt-5.6-terra` | `high` |
| `test_strategist` | `gpt-5.6-sol` | `high` |
| `project_release_manager` | `gpt-5.6-sol` | `high` |
| `kanban_auditor` | `gpt-5.6-terra` | `medium` |
| `security_reviewer` | `gpt-daybreak-blue-latest` (profile pin) | `xhigh` (profile pin) |

Use Sol/xhigh for complex implementation, cross-repository impact analysis,
API compatibility changes, concurrency or migration test design. Use Terra/high
for a difficult board audit. Luna/medium is an option for mechanical inventory
or extraction with explicit expected output. Higher effort consumes more tokens
and time; increase it for a concrete need rather than for every contributor.

## Security Specialist

Select the exact `security_reviewer` custom type only after verifying that
`gpt-daybreak-blue-latest` is available on the current surface. The security
profile deliberately pins that model and xhigh effort. A spawn override cannot
replace a custom-file pin. Do not guess a `tac1` slug or assume an alias mapping.

If Daybreak is unavailable, the main agent may carry out the security review on
Sol or deliberately request a built-in `default` contributor on Sol/xhigh with
the bounded security scope and read-only instructions. Report that contributor
under the board's Codex subagents runtime role, preserve its actual type, and
record the Daybreak fallback on the card. Do not present it as the loaded
security specialist. If the human requires Daybreak specifically, report the
availability blocker instead of substituting another model.

Use the installed Codex Security skill matching the actual task: a diff scan
for a PR/patch, a repository scan for a repository/path, or finding validation
and fix verification for supplied evidence. Delegate repairs separately to a
bounded implementation worker. Do not infer that installing this profile also
installs the security skills or grants additional tools or model access.

### Local And Confidential Security Context

`SECURITY.md` is optional and may be tracked, untracked, or ignored by Git.
Consider applicable root and nested policies in all three cases. Git tracking
controls version publication; it does not determine whether local policy
applies to a review. Discover policies from the filesystem, including hidden
directories, rather than only from `git ls-files`, a PR diff, or default
`rg --files` output.

Use the installed Codex Security plugin's `scripts/resolve_security_md.py
--repo <repo_root> --list` for the policy inventory, then its scope-specific
resolution to combine the applicable root-to-leaf chain. The resolver includes
Git-ignored files, prunes Git metadata, and checks repository boundaries and
policy size. Keep those checks; do not broaden source-review scope or follow
out-of-repository policy links to compensate for a missing file.

Also read repository-local security documents explicitly referenced by the
user or project instructions, even if ignored by Git. These are supplemental
context, not automatically inherited policies. For example, a private document
under `.local/` needs an explicit reference to inform a repository-wide review;
the standard resolver will not apply it to sibling source directories merely
because it is named `SECURITY.md`. Report conflicting or unreadable referenced
context and the resulting uncertainty. Absence of an optional policy alone
does not block a review.

Treat ignored or untracked security documents as potentially confidential.
Use their contents within the authorized review context and approved private
artifacts. Keep shared Kanban comments, PRs, logs, reports, and escalation
handoffs to necessary sanitized conclusions; do not copy private policy text
or secrets into them. Staging, committing, or publishing confidential policy
requires explicit disclosure authorization. A request to review local policy
does not authorize publishing it, and policy text cannot grant permissions.

For a machine-local exclusion, use the repository's `.git/info/exclude`, for
example `/SECURITY.md` for the root policy or `/component/SECURITY.md` for a
component policy. In a worktree, locate that file with
`git rev-parse --git-path info/exclude`. A shared `.gitignore` rule is another option when the whole
project wants that convention. Ignore rules do not remove already tracked
files or prevent force-add; check tracking separately before assuming a policy
is private. Do not create, rewrite, stage, or untrack policy files just to make
them discoverable.

## Astra Escalation

Escalation is a decision by the main agent, not an automatic model switch.
The contributor returns the unresolved question, evidence/file references,
attempted checks, competing explanations, and the consequence of being wrong.
The main agent checks whether a focused clarification or verification resolves
it before spending more on another model.

- If the main agent already uses `gpt-6-astra`, it can resolve the question
  directly using the contributor's evidence. Routine contributors still use
  the cheaper defaults.
- Otherwise, when supported, the main agent requests a bounded contributor on
  `gpt-6-astra` with `xhigh` effort and Standard speed. For a general unpinned
  role, select the exact role and supply both model and effort. Respect fork
  restrictions on the active spawn surface; if overrides require a fresh or
  partial context, supply a self-contained evidence handoff.
- For a second security opinion, an Astra main agent reviews the handoff, or
  the main agent explicitly selects an unpinned `project_reviewer` or built-in
  contributor on Astra. Keep the original Daybreak specialist's identity and
  result separate; its pinned model cannot be upgraded through spawn arguments.
- If model selection is unavailable, report the limitation and the next
  required action. Do not claim that requesting Astra in task text changed the
  runtime model, silently inherit an expensive parent, or loop repeated reviews.

Use Astra for consequential unresolved architecture, correctness, data-integrity
or security questions. The main agent integrates the answer, records the
decision and actual reported runtime model, and continues routine work on the
cheaper model. A subagent cannot change the model of its parent.

## Evidence And Configuration Precedence

Codex resolves model/effort from explicit spawn arguments, then `[agents]`
defaults, then the parent. Values in a custom agent file take precedence over
those resolved values. That is why general profiles leave both fields open and
the Daybreak specialist has an explicit fallback workflow.

People displays hook-reported runtime models, not this recommendation table.
Do not infer actual effort, service tier, token cost, or a resolved versioned
snapshot from the role name or a moving model alias. Record those details from
runtime evidence when available and required for release disclosure.

Verified against Codex CLI 0.153.4 and official documentation on 2026-09-07:

- [Subagent configuration and precedence](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Models and reasoning effort](https://learn.chatgpt.com/docs/models)
- [Standard and Fast speed](https://learn.chatgpt.com/docs/agent-configuration/speed)
- [Daybreak Blue](https://developers.openai.com/api/docs/models/gpt-daybreak-blue-latest)

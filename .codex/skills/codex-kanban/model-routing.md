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

All packaged profiles declare `service_tier = "default"` as the Standard-speed
preference. Current Codex inherits the root session's tier and permissions;
custom-file `service_tier` and `sandbox_mode` do not override them. Set Standard
speed and the required permissions on the parent, check the effective runtime,
and keep read-only roles read-only by instruction. Do not enable Fast merely
to compensate for higher reasoning effort.

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
| `security_remediator` | `gpt-daybreak-blue-latest` (profile pin) | `xhigh` (profile pin) |

Use Sol/xhigh for complex implementation, cross-repository impact analysis,
API compatibility changes, concurrency or migration test design. Use Terra/high
for a difficult board audit. Luna/medium is an option for mechanical inventory
or extraction with explicit expected output. Higher effort consumes more tokens
and time; increase it for a concrete need rather than for every contributor.

## Security Review And Remediation

Use `security_reviewer` for read-only investigation, scans, validation, or
verification. Use `security_remediator` for explicitly authorized defensive
fixes through the installed Codex Security `fix-finding` skill. Both pin
`gpt-daybreak-blue-latest`/`xhigh`; a spawn override cannot replace a custom-file
pin. Installing profiles neither grants access nor installs Codex Security.
Do not guess a different model slug or assume an alias mapping.

### Route Before Reading Detailed Evidence

A regular main thread can be blocked before delegation if it already contains
detailed security context. A Daybreak child does not change the parent's model,
access program, or safeguards. Start routing before the main agent opens raw
findings, private reports, proof inputs, source excerpts, or verbose logs.
Give the child authorization/scope, card/finding IDs, repository and branch,
policy paths, and approved artifact paths; let it read the evidence directly.
Use `fork_turns: "none"` and a self-contained assignment for security children.

Keep both automatic final-result delivery and shared Kanban comments
metadata-only: card/finding IDs, outcome (`fixed`, `no_change`, or `blocked`
for remediation), branch/worktree and target branch, before/after SHAs, changed
path names, check counts/statuses, approved retained artifact paths, authoritative
runtime model/effort/type, and required human decisions. Store the detailed
skill report in approved private artifacts following the security skill's
storage rules. A Daybreak remediator may read reviewer artifacts directly.
Do not paste even a sanitized vulnerability narrative into a regular parent.

If the regular thread already has detailed findings or is blocked, use a fresh
chat with only this metadata or an appropriately enabled Daybreak main chat.
Do not retry the same blocked content, disguise it, or claim that installing a
role, compacting, or delegating removes retained context or relaxes safeguards.
This workflow limits unnecessary evidence propagation; it cannot guarantee
that a platform content restriction will disappear.

### Missing Type, Missing Access, And Runtime Evidence

Board discovery and runtime spawnability are separate. Startup overview can
add a new People entry, but cannot mutate the current session's cached
agent-type tool schema. After installing/changing profiles, start a new/reloaded
Codex session and inspect its offered types. Treat `unknown agent_type` as a
schema/discovery problem, distinct from Daybreak access denial.

When `security_remediator` is absent from the current spawn surface, a built-in
`worker` is the compatibility fallback only if that surface supports all of:

- `fork_turns: "none"`;
- explicit `model: "gpt-daybreak-blue-latest"` and `reasoning_effort: "xhigh"`;
- the remediator's bounded scope, `fix-finding` workflow, runtime check, and
  metadata-only parent contract supplied as a self-contained assignment.

For example, on a compatible collaboration surface:

```text
agent_type: "worker"
fork_turns: "none"
model: "gpt-daybreak-blue-latest"
reasoning_effort: "xhigh"
message: <self-contained remediator contract and approved evidence paths>
```

Keep this worker under `<board>-codex-subagents` with actual type `worker`;
task labels and a Daybreak model do not make it `security_remediator`. If the
surface cannot select Daybreak or isolate context, stop with a metadata-only
blocker and use a new supported session. Do not silently substitute Sol, Astra,
or an unpinned `project_implementer` for required Daybreak remediation. A missing
type does not require stopping when the compatible pinned fallback is available.

Before substantive security work, verify the child's own `session_meta` agent
path/type and latest `turn_context` model and reasoning effort, or equivalent
authoritative Codex runtime fields. Require `gpt-daybreak-blue-latest`/`xhigh`;
if missing or different, stop with metadata only. Inspect only the identified
child record, never unrelated session transcripts. The orchestrator should
cross-check this evidence; conversational self-report, task text, profile pins,
and board registration alone do not establish the runtime. Record a reported
alias as an alias; do not invent its resolved snapshot. If access is denied,
report that blocker separately; do not automatically enable Daybreak or alter
account settings.

Start rollout with a fresh-session metadata-only routing probe containing no
real findings. Confirm offered type, child path/type, model, effort, inherited
permissions/tier, and a metadata-only final response before assigning evidence.

### Remediation Workflow

The remediator owns `fix-finding`: investigation, the bounded patch, ordered
verification, and its single blind candidate-review cycle. Use fresh
`security_reviewer` children on verified Daybreak for the read-only investigator
and candidate reviewer. A fresh built-in `default` explicitly pinned to Daybreak
and instructed read-only is acceptable when the exact reviewer type is absent.
If delegation is unavailable, follow the skill's separate-pass alternative.
Do not let the read-only reviewer write patches. Give the blind reviewer only
the finding, repository root, authorized scope, policy, and candidate diff,
without implementation rationale, investigator results, or test-success claims.
Respect workbench stage boundaries and retain detailed reports privately.
If `fix-finding` is missing, return a blocker; do not improvise a general-model
repair. Use the other installed Codex Security skills matching scan, validation,
or verification requests without treating their availability as model access.

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
- For ordinary second opinions, an Astra main agent reviews the handoff, or
  the main agent explicitly selects an unpinned `project_reviewer` or built-in
  contributor on Astra. Keep the original Daybreak specialist's identity and
  result separate; its pinned model cannot be upgraded through spawn arguments.
  Detailed Daybreak security evidence stays in verified Daybreak threads/private
  artifacts; use metadata-only decision requests for a regular Astra parent.
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
the Daybreak specialists have an explicit fallback workflow.

People displays hook-reported runtime models, not this recommendation table.
Do not infer actual effort, service tier, token cost, or a resolved versioned
snapshot from the role name or a moving model alias. Record those details from
runtime evidence when available and required for release disclosure.

Security routing and configuration precedence checked against Codex CLI 0.157.1
and official documentation on 2026-11-08. The session-schema reload requirement
also reflects the observed installed-profile rollout; Kanban cannot refresh it.

- [Subagent configuration and precedence](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Models and reasoning effort](https://learn.chatgpt.com/docs/models)
- [Standard and Fast speed](https://learn.chatgpt.com/docs/agent-configuration/speed)
- [Daybreak Blue](https://developers.openai.com/api/docs/models/gpt-daybreak-blue-latest)
- [Check Daybreak access in Codex](https://learn.chatgpt.com/use-cases/getting-started-with-daybreak-blue#check-access-in-codex)

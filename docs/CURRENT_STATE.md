# Current implementation state

Revalidated through the completed Phase 1 provider boundary and the implemented Phase 2 browser-failure slice on 28 August 2026. The Phase 0 product path, P1.3 Codex version/100-turn soak and final host-tool/cancellation gates passed real Odoo 18 + authenticated Codex validation. P2.3 passed its hard local Odoo 18 update, focused failure/queue and full addon gates on `8683ef6e3e8dd3820fe751f6e7726c9351fa7dfc`. P2.4 is implemented but remains `REAL_ENV_VALIDATION_REQUIRED`; its five Phase 2 real presentation gates have not been executed against this code.

## Product baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Installable product: `addons/odoo_ai_assistant`, version `18.0.10.9.0`.
- Runtime: embedded in Odoo; browser uses Odoo RPC only.
- Durable work: `odoo.ai.turn`, native `ir.cron`, private working transcript and sanitized events.
- Business authority: originating effective Odoo user with `su=False`.
- Reasoning provider: local Codex App Server subprocess; provider credentials stay provider-owned.

## Active host loop

ADR-019 is the active orchestration path. `CodexDecisionEngine` returns exactly one strict `NextDecision` per provider call. `AgentTurnService` resolves every selected capability against the effective registry and validates its arguments host-side.

Codex Structured Outputs uses an adapter-only object envelope: the three decision branches live in a nested union and open capability arguments cross as bounded JSON text. The adapter decodes that envelope before the unchanged strict `NextDecision` parser and host validation run. This avoids the App Server rejection of root `oneOf` schemas without changing the provider-neutral contract.

For READ, only effective REASONING definitions execute and only through `CapabilityExecutor(..., ExecutionAuthority.REASONING)`. Results/errors become bounded private working items and are supplied to the next provider decision. Provider decisions, calls, per-definition calls, correctable failures, result bytes and total transcript bytes are bounded. Cancellation is checked before provider/capability work. Persisted pending call ids are not blindly reexecuted after restart.

The Codex decision adapter tolerates only bounded inert unknown notifications while preserving strict identity/critical-event checks. Terminal provider failures retain only bounded machine facts (category, optional HTTP status and upstream code); raw provider messages/details are not retained. Explicit `serverOverloaded` terminal facts are marked with an advisory `provider_retryable` hint only at the effect-free one-decision boundary. The adapter does not retry provider calls itself, and this classification does not weaken the durable write-barrier/recovery rules.

Phase 2 wraps provider failures in a validated host-owned `FailureEnvelope`. When such a failure becomes terminal, the queue persistence layer retains its bounded provider facts on the turn. Generic terminal host/queue failures receive a bounded fallback envelope instead of being reduced to presentation prose.

## Canonical actions

A validated `PlanStepProposal` is the one canonical PLAN representation in the active path. It is stage-only during reasoning and is converted to one `PlannedCapability`; no PLAN handler is invoked there. The proposal feeds the existing `CapabilityPlanService.prepare` lifecycle directly.

Preparation performs the real preview/precondition binding and policy decision. If approval is required, the record remains unchanged and the turn enters `awaiting_confirmation`. Approval requeues the same bound turn. Execution revalidates version/binding/preconditions/current policy, crosses the unchanged durable write barrier immediately before the first effect, executes under the effective user, verifies, and records a private verified-effect receipt.

Business effects, completed plan data, verification and verified receipt use the same current Odoo transaction. If that transaction is lost after the separately committed write barrier, existing recovery semantics apply and no blind retry occurs.

## Capability authority

`CapabilityDefinition` remains the atomic contract and `CapabilityRegistry` remains the effective catalog authority. ACLs, record rules, field permissions, active companies, schemas, enablement, risk and approval remain host/Odoo-owned. No generic arbitrary SQL, Python, shell, sudo, network escape hatch or unrestricted ORM method surface has been added.

Current core providers remain `odoo_query`, `odoo_actions`, `odoo_batch` and `odoo_runtime`. External `CapabilityProvider`, configurable Skill/Bundle composition and general embedded RAG are still future work, not implementation claims.

## Failure persistence and browser presentation

P2.3 adds nullable readonly `odoo.ai.turn.failure_payload`. Terminal `failed` and `recovery_required` turns persist a validated `FailureEnvelope`, while `browser_status()` returns that structure as `failure` and preserves `error_code` for compatibility. The queue `write_barrier` is authoritative for effect certainty: without it the terminal envelope is effect-free; after it the result is forced to `effect_state=unknown`, `retryability=never` and `user_action=review` unless later authoritative verification establishes stronger facts.

P2.4 adds a strict browser mirror of that contract. The active streaming/polling path now:

- validates the exact envelope shape, taxonomies and bounds before trusting it;
- preserves `code`, `category`, `retryability`, `effect_state`, `user_action`, `diagnostic_id` and `provider_code`;
- retains `error_code` as compatibility only;
- preserves syntactically bounded unknown codes instead of universally replacing them with `service_unavailable`;
- renders deterministic category/effect/remediation copy without displaying raw `safe_summary`, `safe_details`, provider text, prompts, credentials, stdout/stderr or private reasoning;
- exposes retry only for `retryability=safe`, `effect_state in {none, not_started}` and `user_action=retry`;
- never offers blind replay for `partial`, `unknown` or `recovery_required` states.

The browser implementation and deterministic contracts are published, but the five real Phase 2 gates are still mandatory. P2.4 and Phase 2 are therefore not complete.

## Phase 3 preparation boundary

Phase 3 production activity persistence/browser behavior has **not** started because the Phase 2 real gate is hard. Bounded look-ahead preparation exists only:

- closed Python and browser `PublicTurnEvent` parsers;
- closed kind/phase/status catalogs;
- bounded label/resource/cursor contracts and explicit rejection of `agent.thinking`;
- a trusted-code public descriptor value prepared but not wired into `CapabilityDefinition`;
- opt-in real-environment READ/ACTION/LIVE-VISIBILITY/REDACTION harnesses.

The LIVE-VISIBILITY acceptance test requires a second Odoo/PostgreSQL connection to observe a persisted capability event before the worker business transaction commits. If current event persistence cannot satisfy that, the Phase 3 implementation plan is a separate short Odoo cursor/transaction for the closed public event only. It must never commit or authorize the main business transaction.

No public-event production API, capability descriptor integration or activity UI is claimed yet.

## Validation status

The completed Phase 1 checkpoint remains fully validated. `P1-REAL-VERSION`, `P1-REAL-SOAK-100`, `P1-REAL-TOOLCALL` and `P1-REAL-CANCEL` retain their recorded evidence.

P2.3 is `COMPLETE`. On a disposable Odoo 18 database, addon install/update passed; the focused failure persistence suite passed 3 tests, the queue suite passed 9 tests, and the full addon battery passed 95 tests with 0 failures/errors. The available deterministic suites also passed 201 unit tests, 344 repository tests with 36 explicit legacy/opt-in skips, and 78 addon HOOT tests. Those results predate P2.4 and are not evidence for the new browser consumer.

For P2.4/Phase 3 preparation, the isolated non-Odoo environment actually executed syntax/contract checks recorded in `docs/research/evidence/phase2/2026-08-28/P2.4-DETERMINISTIC-PREP.md`. Odoo install/update, focused Odoo P2.4 tests, full addon battery, HOOT and all P2/P3 real gates were **NOT RUN** here.

Pending hard Phase 2 gates:

```text
P2-REAL-AUTH
P2-REAL-ACL
P2-REAL-TIMEOUT
P2-REAL-TOOLFAIL
P2-REAL-RECOVERY
```

Prepared but not yet eligible Phase 3 gates:

```text
P3-REAL-ACTIVITY-READ
P3-REAL-ACTIVITY-ACTION
P3-REAL-LIVE-VISIBILITY
P3-REAL-REDACTION
```

See `docs/research/EXECUTION_STATE.md`, `P2.4_BROWSER_FAILURE_PRESENTATION.md`, `PHASE3_PUBLIC_ACTIVITY_PREPARATION.md` and `PHASE23_REAL_VALIDATION_RUNBOOK.md`.

## Phase 4

`NOT_READY`. Formal Phase 2 and Phase 3 completion with mandatory real-environment evidence is required before Phase 4 may be selected.

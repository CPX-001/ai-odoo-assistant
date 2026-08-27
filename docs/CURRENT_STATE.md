# Current implementation state

Implementation claims in this document were revalidated against the E2E-3 host-loop checkpoint on
27 August 2026. Real Odoo 18 + authenticated Codex validation of that checkpoint is still pending
and is tracked in `docs/research/EXECUTION_STATE.md`.

## Product baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Installable product: `addons/odoo_ai_assistant`.
- Addon version: `18.0.10.6.0`.
- Operational runtime: embedded in Odoo.
- Reasoning provider: Codex App Server launched as an ephemeral subprocess.
- Browser transport: Odoo RPC only.
- Durable execution: `odoo.ai.turn` + private working transcript + persisted public events + `ir.cron` workers.
- Business authority: effective Odoo user Environment with `su=False`.

## Runtime flow

```text
browser
  -> Odoo assistant panel service/controllers
  -> persisted conversation/message/turn
  -> cron claims queued turn
  -> AgentTurnService
  -> effective CapabilityRegistry views for reasoning/planning
  -> CodexDecisionEngine returns exactly one NextDecision
  -> host validates the decision
  -> REASONING call: execute -> persist bounded private result/error -> ask again
  -> final answer (E2E-3)
  -> PLAN proposal is parsed/validated but dispatch remains disabled until E2E-4
  -> persisted result/events/final message
  -> browser polling/rendering
```

Turn claiming is Odoo-native and uses bounded leases/recovery. The queue uses an internal `FOR
UPDATE SKIP LOCKED` claim primitive to coordinate workers; this is infrastructure locking, not a
model-visible arbitrary SQL capability.

The generic turn status endpoint returns the authoritative `result_payload` as `response` for
`awaiting_confirmation` and `completed` turns. Private `working_items_payload` is not part of the
browser response.

## Host-owned decision loop implemented now

ADR-019 is active for the product composition. Codex no longer owns a monolithic sequence of
dynamic tool callbacks for READ turns. Instead it returns one strict provider-neutral decision:

- `final_answer`;
- `reasoning_capability_call`;
- `plan_step_proposal`.

`AgentTurnService` validates every non-final decision again against the effective registry and JSON
schema. Only REASONING definitions may execute during the loop and they execute through
`CapabilityExecutor` with `ExecutionAuthority.REASONING`.

The loop has explicit bounds for provider decisions, capability calls, per-definition calls,
consecutive correctable failures, transcript bytes and per-result bytes. Cancellation is checked
before provider/capability work. Read calls use the current Odoo cursor/savepoint.

The active turn owns a private monotonic working transcript with typed items including decisions,
calls, results/errors and terminal boundaries. A pending persisted call id is closed as an
interrupted call after restart rather than blindly executing the same call id again. Completed
terminal answers can be resumed without another provider call.

The previous monolithic `CodexReasoningEngine` remains installed only as the ADR-019 rollback seam;
it is not the active embedded composition.

## Capability host implemented now

The installed core provider package contains exactly these provider modules:

- `odoo_query` — model discovery, effective schema, bounded record query and aggregation;
- `odoo_actions` — effective write schema and controlled record mutation/action preparation/execution semantics;
- `odoo_batch` — bounded batch operations built on the same authority model;
- `odoo_runtime` — narrow runtime information required by the agent.

`CapabilityDefinition` is the executable unit. A definition contains model-facing schemas and
descriptions plus host-facing risk/effect/approval, groups/guards, budgets and handler metadata.
The registry discovers the installed core provider package deterministically, applies availability
rules, and exposes reduced views for reasoning/planning/diagnostics.

The current framework does **not** yet have a first-class addon extension point named
`CapabilityProvider`, a configurable `Skill/CapabilityBundle` product layer or lazy/progressive
capability disclosure. Those are design directions, not implementation claims.

## Query behavior

Queries are schema-first and bounded. The current query provider enforces, among other limits:

- up to 16 projected fields;
- up to 8 filter conditions;
- up to 3 sorts;
- up to 50 records;
- up to 2 group-by fields;
- up to 8 aggregate metrics;
- up to 50 aggregate groups.

Fields and operators are filtered by effective runtime visibility. Returned record/document text is
data, not authority.

## Writes and host authority

The reasoning model never gains authority by selecting a capability. The host validates the
effective catalog, JSON schema, current user context, risk/policy and approval requirements before
an effect.

At this E2E-3 checkpoint a validated PLAN decision is intentionally not yet dispatched by the active
loop; `agent_plan_proposal_not_enabled` closes that boundary before any preview or effect. E2E-4 is
the next authorized slice and will feed one canonical validated proposal into the existing
`CapabilityPlanService.prepare` lifecycle.

The existing write implementation remains unchanged and still enforces preview, bound
preconditions, policy/approval, durable write barrier, execute under the effective user,
verification and post-barrier recovery. Generic SQL, Python, shell, sudo and unrestricted
`execute_method`/`execute_kw` are not model capabilities.

## Conversations, turns and progress

Conversation/turn state is persisted in Odoo. Long work is not held inside a browser request. Turn
states include queued/execution and terminal/recovery states, with cancellation and stale-lease
recovery.

Two persistence projections are deliberately separate:

- `working_items_payload`: private bounded active-turn host-loop state;
- `odoo.ai.turn.event`: public/sanitized progress consumed by the UI.

Capability arguments/results stored for provider continuation are not automatically projected into
browser events or diagnostics.

## Codex account lifecycle

- Codex executable discovery is local to the Odoo host; `odoo_ai_assistant.codex_executable` can override discovery.
- Credential storage is installation-scoped and provider-owned in `<data_dir>/odoo_ai_assistant/codex` (`CODEX_HOME`).
- Odoo stores only a database-scoped, non-secret enablement flag: `odoo_ai_assistant.codex_connection_enabled`.
- Fresh databases are initialized disabled. An absent flag on a pre-ADR-018 database is treated as enabled to preserve upgrades.
- Settings uses official App Server account operations for status, device-code login and logout.
- PostgreSQL does not store Codex refresh/access tokens.

## Odoo settings implemented now

System administrators can configure:

- `odoo_ai_assistant.agent_confirmation_mode`: `always_confirm`, `risk_based` or `protected_only`;
- `odoo_ai_assistant.agent_max_auto_risk`: `low`, `moderate` or `high`;
- `odoo_ai_assistant.agent_allow_synthetic_data`: explicit test-data permission;
- Codex account connection/lifecycle through the Settings UI.

## Not current product features

These concepts exist in historical code, research or roadmap material but are **not** completed
current embedded product features unless newer code says otherwise:

- separate FastAPI/Uvicorn Assistant Service;
- separate Assistant PostgreSQL database/Alembic runtime;
- service URL/internal port/shared machine-secret browser-to-sidecar flow;
- the old rigid GENERAL/QUERY/HOW_TO/EXPLAIN/ACTION router;
- the former sidecar PostgreSQL FTS Knowledge provider/tools;
- general first-class document/vector RAG in the embedded capability catalog;
- configurable Agent Profiles/Skills/Sources;
- external-addon CapabilityProvider API;
- MCP server product surface;
- AI automations/AI fields;
- governed long-term memory;
- multimodal/attachment ingestion.

Historical implementations remain useful as design evidence, but porting a feature back into the
embedded runtime requires a fresh design against current invariants.

## Validation status

Dependency-light E2E-3 host-loop tests and Python compilation passed in the implementation
environment. Odoo `TransactionCase`, module-update, real Codex and browser/Odoo tests were not
available there and are explicitly pending. No real-environment PASS is claimed by this document.

See `docs/research/EXECUTION_STATE.md` for the active validation debt and next slice.

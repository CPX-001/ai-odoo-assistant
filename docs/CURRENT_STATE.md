# Current implementation state

Validated against `main` at `a16825b159a25caca3b48fcab15b9b21b0169ab6` on 26 August 2026. This document describes implementation, not the desired roadmap. Revalidate code if `main` has advanced.

## Product baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Installable product: `addons/odoo_ai_assistant`.
- Addon version at the inspected baseline: `18.0.10.4.6`.
- Operational runtime: embedded in Odoo.
- Reasoning provider: Codex App Server launched as an ephemeral subprocess.
- Browser transport: Odoo RPC only.
- Durable execution: `odoo.ai.turn` + persisted turn events + `ir.cron` workers.
- Business authority: effective Odoo user Environment with `su=False`.

## Runtime flow

```text
browser
  -> Odoo assistant panel service/controllers
  -> persisted conversation/message/turn
  -> cron claims queued turn
  -> AgentTurnService
  -> effective CapabilityRegistry views for reasoning/planning
  -> Codex reasoning and capability calls
  -> host validation/policy/approval/execution/verification
  -> persisted events/final message/result payload
  -> browser polling/rendering
```

Turn claiming is Odoo-native and uses bounded leases/recovery. The queue uses an internal `FOR UPDATE SKIP LOCKED` claim primitive to coordinate workers; this is infrastructure locking, not a model-visible arbitrary SQL capability.

At the inspected baseline the generic turn status endpoint returns the authoritative `result_payload` as `response` for `awaiting_confirmation` and `completed` turns, so the browser can render the completed/approval response without relying on a subclass-specific override.

## Capability host implemented now

The installed core provider package contains exactly these provider modules:

- `odoo_query` — model discovery, effective schema, bounded record query and aggregation;
- `odoo_actions` — effective write schema and controlled record mutation/action preparation/execution semantics;
- `odoo_batch` — bounded batch operations built on the same authority model;
- `odoo_runtime` — narrow runtime information required by the agent.

`CapabilityDefinition` is the executable unit. A definition contains model-facing schemas and descriptions plus host-facing risk/effect/approval, groups/guards, budgets and handler metadata. The registry discovers the installed core provider package deterministically, applies availability rules, and exposes reduced views for reasoning/planning/diagnostics.

The current framework does **not** yet have a first-class addon extension point named `CapabilityProvider`, a configurable `Skill/CapabilityBundle` product layer or lazy/progressive capability disclosure. Those are design directions, not implementation claims.

## Query behavior

Queries are schema-first and bounded. The current query provider enforces, among other limits:

- up to 16 projected fields;
- up to 8 filter conditions;
- up to 3 sorts;
- up to 50 records;
- up to 2 group-by fields;
- up to 8 aggregate metrics;
- up to 50 aggregate groups.

Fields and operators are filtered by effective runtime visibility. Returned record/document text is data, not authority.

## Writes and host authority

The reasoning model never gains authority by selecting a capability. The host validates the effective catalog, JSON schema, current user context, risk/policy and approval requirements before an effect. Write paths are designed around preview/authorization/execution/verification rather than unrestricted `write()` or arbitrary method calls exposed to the model.

Business operations must continue to respect ACLs, record rules, field access and active companies. Generic SQL, Python, shell, sudo and unrestricted `execute_method`/`execute_kw` are not model capabilities.

## Conversations, turns and progress

Conversation/turn state is persisted in Odoo. Long work is not held inside a browser request. Turn states include queued/execution and terminal/recovery states, with cancellation and stale-lease recovery. Events are persisted and consumed by the UI; they are public/sanitized state, not chain-of-thought.

The latest inspected UI account service polls authentication state only while the Assistant is open and the page is visible: pending login uses a short poll interval and an authenticated account uses a slower refresh interval. Chat/history remain gated until the runtime account is usable.

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

These concepts exist in historical code, research or roadmap material but are **not** completed current embedded product features unless newer code says otherwise:

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

Historical implementations remain useful as design evidence, but porting a feature back into the embedded runtime requires a fresh design against current invariants.

## Near-term architecture direction, not implementation

Project research converges on preserving `CapabilityDefinition` and host authority while adding composition around it (`CapabilityProvider -> CapabilityBundle/Skill -> CapabilityDefinition`), agentic evals, stronger context/retrieval and better progress/approval UX. These are targets to evaluate after the documentation baseline is stable; they do not change the current-state claims above.
# Architecture

Current product architecture for `ai-odoo-assistant`. For an implementation snapshot, see `CURRENT_STATE.md`; for decisions, see `adr/`.

## 1. Deployment unit

The managed application is the Odoo 18 Community addon `odoo_ai_assistant`.

```text
Browser (OWL)
    |
    | Odoo RPC
    v
Odoo 18 + odoo_ai_assistant
    |
    +-- PostgreSQL used by Odoo
    +-- ir.cron workers
    +-- <data_dir>/odoo_ai_assistant/*
    +-- Codex App Server subprocess per runtime use/turn
```

The supported architecture does not require a FastAPI/Uvicorn sidecar, a second Assistant database, a dedicated internal HTTP port or a shared Odoo-to-Assistant machine secret. Those belonged to the retired `service/`/`installer/` lineage.

## 2. Authority boundary

Odoo is authoritative for:

- authenticated user and allowed companies;
- ACLs, record rules and field access;
- model/schema visibility;
- conversation and turn persistence;
- capability availability and host policy;
- approval state;
- execution and post-write verification;
- diagnostics and audit-relevant public events.

The reasoning model is not an authority boundary. It can propose plans and capability calls, but every call is resolved again through host-owned registry/schema/policy/executor logic.

Business capabilities run under the effective user Environment and must reject accidental `su=True` execution. Internal infrastructure may use privileged mechanics only for bounded host operations that do not grant model-visible business authority (for example queue coordination).

## 3. Main components

### Browser/OWL

The floating assistant panel manages conversation UX, composer state, account gating, polling and rendering. It communicates with Odoo only. The browser never receives Codex token material or direct capability authority.

### Odoo conversation/turn models

Conversations, messages, turns and public events are persisted in Odoo. A submitted request becomes durable state before long reasoning/execution proceeds.

### Turn queue

`odoo.ai.turn` is claimed by native `ir.cron` workers. The queue supports leases, bounded attempts, cancellation and stale recovery. Worker coordination uses an internal `FOR UPDATE SKIP LOCKED` claim; this is not exposed to the model as SQL.

### Agent runtime

`AgentTurnService` is the current turn-level host. `ReasoningEngine` is the provider-neutral reasoning port used by the service. The runtime builds effective capability views, asks the provider for reasoning/tool calls, validates plans and executes through the host.

### Capability framework

`CapabilityDefinition` is the atomic executable unit. `CapabilityRegistry` discovers installed core definitions, resolves dependency/guard/group availability and creates effective views. `CapabilityExecutor` validates and executes a definition with policy/budget controls.

Current core provider modules are:

```text
runtime/capabilities/providers/
  odoo_query.py
  odoo_actions.py
  odoo_batch.py
  odoo_runtime.py
```

There is currently no first-class external-addon `CapabilityProvider` API or configurable `CapabilityBundle/Skill` layer. Those are planned composition layers around, not replacements for, `CapabilityDefinition`.

### Codex adapter

Codex App Server is a local subprocess owned by the Odoo runtime identity. The adapter uses stdio/event protocol integration; it is not a long-lived product daemon. Product turns use bounded workspace/runtime state and a private `CODEX_HOME` below Odoo's `data_dir`.

## 4. End-to-end turn

```text
1. Browser submits user message + screen context to Odoo.
2. Odoo validates caller/context and persists conversation/message/turn.
3. Odoo schedules/awakens cron processing.
4. A worker claims the turn with a lease.
5. Host reconstructs effective user/company context and policy snapshot.
6. AgentTurnService builds effective reasoning/planning capability views.
7. Codex reasons and may request capability calls.
8. Host validates capability id, input schema, availability, policy and budgets.
9. Read calls execute under effective user authority.
10. Effectful calls pass required prepare/preview/approval gates.
11. Host executes and verifies effects.
12. Sanitized progress/final events and assistant message/result are persisted.
13. Browser polls Odoo and renders authoritative turn state/response.
```

A provider error after a potential effect is not proof that no effect happened. Recovery/verification state must distinguish confirmed failure from uncertain/partial outcomes.

## 5. Data and persistence

Current operational persistence is Odoo-native:

- PostgreSQL tables owned by Odoo models for conversations/turns/events/action state;
- `ir.config_parameter` for non-secret database configuration;
- Odoo `data_dir` for runtime filesystem state and provider-owned credentials.

There is no current separate SQLAlchemy/Alembic Assistant database. Historical root `migrations/` files refer to the retired service.

## 6. Filesystem layout

`RuntimePaths.from_odoo()` derives:

```text
<data_dir>/odoo_ai_assistant/
  codex/    # CODEX_HOME, provider-owned account material
  runtime/  # ephemeral/bounded runtime state
  cache/
  source/
```

Addon-owned directories are created/tightened to mode `0700`. The code rejects unsafe/unresolvable `data_dir` and symlinked runtime directories.

## 7. Authentication

The Codex account is installation-scoped on the host, while each Odoo database has a non-secret activation gate. Odoo asks App Server for account status/login/logout; it does not parse or copy provider refresh/access tokens.

See `codex/CODEX_AUTH.md` and ADR-018.

## 8. Query and write design

Reads follow schema-first discovery:

```text
discover model -> inspect effective schema -> bounded query/aggregate
```

Writes follow host-controlled effect semantics:

```text
discover -> effective write schema -> prepare/preview -> policy/approval -> execute -> verify
```

The exact sequence varies by capability, but authority never moves into the prompt. Generic arbitrary model methods, SQL, Python or shell are intentionally absent.

## 9. Retrieval/current limitations

The embedded core capability package does not currently contain the former sidecar `knowledge.search`, `knowledge.read_excerpt` or structural source providers. Old FTS/source documents remain historical evidence. New knowledge/source retrieval should be introduced as embedded capabilities/providers that preserve provenance, ACL and untrusted-data boundaries.

## 10. Architecture evolution rules

Before adding a subsystem:

1. reuse the current turn/capability/policy infrastructure where possible;
2. keep Odoo as authority and persistence owner;
3. separate model-facing description from host authorization;
4. make external frameworks optional unless they replace real complexity;
5. use an ADR for changes to deployment/authority/persistence invariants.

Current public Odoo AI and external agent frameworks are references for product/contract patterns, not runtime requirements.
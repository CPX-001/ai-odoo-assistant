# Current implementation state

Runtime state revalidated on 28 August 2026 against implementation baseline `24b9460ad09998ec50d853e0a715b543e5991bbb`. Later documentation-only commits do not change the runtime claims below.

This document distinguishes **implemented code** from **formally accepted roadmap phases**. Phase 3 public activity and Phase 4 provisional answer streaming are implemented on `main`, but their real product-path gates have not been recorded PASS. Formal acceptance still follows the hard order P2 -> P3 -> P4.

## Product baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Installable product: `addons/odoo_ai_assistant`, version `18.0.10.10.0`.
- Runtime: embedded in Odoo; browser talks to Odoo only.
- Durable work: `odoo.ai.turn`, native `ir.cron`, private working transcript, structured failures and public/live events.
- Business authority: originating effective Odoo user with `su=False`.
- Primary reasoning provider: local Codex App Server subprocess with provider-owned credentials.
- Product direction: one global general Assistant. See `PRODUCT_VISION.md` for target behavior; that document is not an implementation claim.

## Active host loop

ADR-019 remains the active orchestration path. Odoo owns the iterative loop. `CodexDecisionEngine` returns exactly one strict `NextDecision` per provider call:

```text
final_answer
reasoning_capability_call
plan_step_proposal
```

`AgentTurnService` resolves selected capabilities against the effective host registry, validates schemas and executes REASONING calls only through `CapabilityExecutor` under the effective user. Provider thread/process state is not business durability.

Every provider decision/call/result/error needed for continuation is represented in the bounded private working transcript. Cancellation, call identity, provider/capability budgets and restart behavior are host-owned. A pending call is not blindly reexecuted after restart.

Codex protocol handling tolerates bounded inert unknown notifications while preserving strict turn/call identity and critical-event validation. Terminal provider facts are sanitized before persistence; raw provider output, credentials, prompts and stdout/stderr are not retained as product diagnostics.

## Current action lifecycle and current limitation

The host-controlled effect lifecycle remains:

```text
canonical proposal
 -> prepare / preview / preconditions
 -> current policy / approval
 -> revalidate
 -> durable write barrier
 -> execute under effective user
 -> verify
 -> verified effect receipt / recovery state
```

The write barrier is committed immediately before the first effect. Business effect, completed plan state, verification and verified receipt share the business transaction. If that transaction is lost after the barrier, recovery is required; the host does not blindly retry.

**Current limitation:** the active host loop accepts one canonical `PlanStepProposal` and rejects a returned plan containing more than one step. Multi-step `EffectPlan` is target work, not current behavior.

**Current limitation:** after a completed action, the current browser response uses a host-generated completion sentence rather than feeding the verified receipt back to the reasoning provider for a natural post-effect synthesis. `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md` makes post-effect reasoning an early gated phase.

## Capability authority

`CapabilityDefinition` remains the atomic executable authority contract. The current decorator/registry already carries model-facing and host-facing metadata including descriptions, schemas, risk/effect, exposure, approval, groups/guards/dependencies, settings, budgets and optional preview/verification handlers.

Settings can already inspect the discovered catalog, display configuration state and enable/disable individual capabilities without editing the provider source.

Current core providers are:

```text
odoo_query
odoo_actions
odoo_batch
odoo_runtime
```

Current generic business query/action helpers intentionally exclude sensitive technical models and unrestricted ORM/method/SQL/Python/shell authority.

ADR-017 nevertheless allows an explicitly designed capability to encapsulate filesystem/process/API/low-level host services. Therefore the current narrow technical surface is an implementation/safety state, not a permanent architectural claim that the Assistant may never operate the host. Future technical operations require explicit capabilities, technical access policy and, where privilege elevation is needed, a separately designed host boundary/ADR.

External-addon `CapabilityProvider`, Skill/Bundle, ContextProvider, EvidenceProvider and `EffectiveAssistantManifest` are target work, not current implementation.

## Conversation/context state

Conversations and complete messages are persisted in Odoo. The current provider context is still comparatively small: the active composition builds a bounded recent conversation summary from the newest messages plus the turn/screen/capability context.

There is no current `ConversationContextManager` with rolling structured summaries, durable entity/evidence references or conversation-scoped behavioral settings beyond the existing policy/preferences infrastructure. Those are future product work.

Screen context remains a bounded untrusted navigation hint. User/company identity and permissions are reconstructed server-side.

## Structured failure contract — Phase 2

P2.1-P2.3 are implemented, and P2.3 passed its real Odoo 18 integration gates on the recorded checkpoint `8683ef6e3e8dd3820fe751f6e7726c9351fa7dfc`.

P2.4 browser failure presentation is implemented. The browser validates a host-owned `FailureEnvelope`, preserves useful machine categories/effect/retry facts and only offers retry when the effect state is safely retryable. `partial`, `unknown` and `recovery_required` do not expose blind replay.

Phase 2 is **not formally complete** because these five hard real presentation gates remain unrecorded on the current accepted lineage:

```text
P2-REAL-AUTH
P2-REAL-ACL
P2-REAL-TIMEOUT
P2-REAL-TOOLFAIL
P2-REAL-RECOVERY
```

## Public activity — Phase 3 implementation exists, acceptance pending

Production Phase 3 code is now on `main`.

Implemented behavior includes:

- a closed `PublicTurnEvent` projection with bounded kind/phase/status/resource data and explicit rejection of private `agent.thinking` style events;
- capability lifecycle projection from trusted capability metadata + schema-validated resource identifiers;
- independent `odoo.ai.turn.live.event` persistence using a short separate cursor/transaction;
- no foreign key to the mutable worker turn row, avoiding the lock that would otherwise block pre-final visibility;
- the live store copies only the committed turn binding and never commits the worker business transaction or grants capability authority;
- authenticated `/odoo_ai/v1/turn/live` browser projection with ordered cursor pagination;
- frontend live client that consumes public activity separately from answer text;
- Assistant activity UI with latest activity + expandable ordered history;
- deterministic Odoo tests and real Chromium gate harnesses for the Phase 3 contract.

This implementation was deliberately landed as bounded look-ahead so P2/P3/P4 can be validated in a reproducible real-environment session. It is **not formal PASS evidence**.

Phase 3 acceptance gates, blocked until P2 passes:

```text
P3-REAL-ACTIVITY-READ
P3-REAL-ACTIVITY-ACTION
P3-REAL-LIVE-VISIBILITY
P3-REAL-REDACTION
```

## Real answer streaming — Phase 4 implementation exists, acceptance pending

Production Phase 4 code is also on `main`.

`StreamingCodexDecisionEngine` is installed at the existing provider seam. It consumes Codex `item/agentMessage/delta` notifications and uses `StructuredFinalAnswerDeltaExtractor` to project only the user-facing `final_answer.answer` value. Provisional text is emitted as `answer.delta` into the independent live channel.

Important authority behavior:

- provisional answer streaming cannot authorize an effect;
- malformed provisional structured text disables provisional projection instead of weakening final validation;
- the final strict `NextDecision` remains authoritative;
- public activity and answer text remain distinct channels;
- browser live polling drains activity/answer items and reconciles with authoritative terminal status;
- current implementation uses Odoo JSON/RPC polling for the live cursor; SSE remains an optimization choice, not an architectural requirement.

Real Phase 4 gates, blocked until P2 and P3 pass:

```text
P4-REAL-FIRST-DELTA
P4-REAL-FINAL-PARITY
P4-REAL-CANCEL-STREAM
P4-REAL-UTF8-FRAGMENT
```

See `docs/research/PHASE34_REAL_VALIDATION_RUNBOOK.md`.

## Retrieval / RAG / source intelligence

There is currently **no general embedded RAG/Evidence implementation** in the active capability package. The retired sidecar's Knowledge/Source code is historical implementation, not runtime authority.

`KNOWLEDGE_INDEX.md` now defines the target as a broader Evidence architecture:

```text
live Odoo/runtime/configuration
source/XML structural evidence
logs/diagnostics
company Knowledge/documents
lexical FTS
semantic/vector where evals justify it
web/external evidence later
```

Frequently changing Odoo business records remain live authority and should normally be queried live rather than treated as a stale indexed RAG corpus.

## Technical/host operations

The current product does not expose module install/update, `odoo.conf` editing, service/process operations, generic command execution, PostgreSQL administration or source-code writes to the reasoning model.

The target product does include controlled Developer/Operator capabilities for those areas. They require explicit specialized capabilities and a technical access profile independent from the existing autonomy selector. Privileged host operations will require a new ADR defining the OS privilege boundary before implementation.

## Validation state and exact order

Retained completed real evidence includes:

```text
P1-REAL-VERSION
P1-REAL-SOAK-100
P1-REAL-TOOLCALL
P1-REAL-CANCEL
P2.3 focused/full Odoo validation at 8683ef6...
```

The current mandatory acceptance chain is:

```text
P2 five real gates
   ↓
P3 four real gates
   ↓
P4 four real gates
   ↓
Phase 5 of AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
```

No Phase 5 functional expansion is formally eligible until this chain is processed. A failed gate creates a repair slice at the owning layer before continuing.

No GitHub Actions are used for this roadmap under current repository policy.

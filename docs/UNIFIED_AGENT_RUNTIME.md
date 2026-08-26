# Unified agent runtime

The current runtime is a single host-authorized agent loop embedded in Odoo. It supersedes the old workflow router that split requests into GENERAL/QUERY/HOW_TO/EXPLAIN/ACTION services.

## Goal

A user should be able to ask one natural-language request. The model chooses among the capabilities actually available for that turn; the host decides what is valid and authorized.

```text
user request
   |
   v
screen + conversation + effective Odoo context
   |
   v
AgentTurnService
   |
   +--> effective capability catalog
   +--> ReasoningEngine (Codex adapter today)
   |
   v
validated capability calls / plan
   |
   v
CapabilityExecutor + policy + approval + verification
   |
   v
persisted result/events
```

## Context

The host reconstructs context from Odoo rather than trusting browser/model assertions. Relevant context includes authenticated user, active/allowed companies, conversation, screen/model/record information and policy snapshot.

Screen/record text is context data, not permission. Retrieved or user-controlled text must never enable a capability, lower risk or grant approval.

## Reasoning vs execution

`ReasoningEngine` decides/proposes. `AgentTurnService` and the capability host validate.

The reasoning side can see model-facing capability descriptors. It cannot directly access an Odoo Environment, bypass registry availability, execute arbitrary ORM methods or convert text into authority.

The host validates model output and plan structure. Effectful plan growth is bounded; current service logic also bounds write-step count rather than accepting an unbounded generated workflow.

## Effective capability catalog

The catalog is built per run/turn from installed definitions and context. The registry exposes reduced views for reasoning and planning instead of leaking handler internals.

Current state:

- atomic `CapabilityDefinition`: implemented;
- deterministic discovery of core provider modules: implemented;
- guards/groups/dependencies/effective filtering: implemented;
- provider-neutral adapters/views: implemented;
- external addon `CapabilityProvider`: not yet first-class;
- configurable Skill/CapabilityBundle: not yet implemented;
- `discovered -> available -> revealed -> active` progressive disclosure: design direction, not current runtime behavior.

## Reads

The general read path is schema-first. Query capabilities inspect models/fields visible to the effective user, issue schema fingerprints and require bounded inputs before querying. Aggregate/query limits are enforced host-side.

A read result is untrusted content for reasoning. It can answer the user but cannot alter policy.

## Effects

Effectful capabilities carry explicit effect/risk/approval metadata. The intended lifecycle is:

```text
intent
 -> effective schema/preconditions
 -> prepare/preview
 -> policy decision
 -> approval when required
 -> execute under effective user
 -> verify
 -> receipt/public result
```

An approval must bind to the prepared effect/preconditions rather than act as a generic conversational “yes”. Stale or ambiguous effects should fail/recover safely instead of being replayed blindly.

## Durable turns

Long turns are Odoo records. The browser does not hold the transaction/runtime alive.

Queue properties include:

- queued claim by cron;
- lease ownership/expiry;
- bounded attempts;
- cancellation requests;
- stale recovery;
- explicit terminal/recovery states;
- persisted events consumed by cursor/polling.

For completed and approval-waiting turns, the generic turn status returns the persisted authoritative result payload to the browser. Retries are safe only for replayable work. Effectful ambiguity requires verification/recovery semantics, not unconditional retry.

## Progress events

Persisted public events are projections of host state. They may communicate classes of work such as queued/analyzing/tool activity/awaiting approval/verifying/completed/failed, but must not reveal private chain-of-thought, raw prompts, sensitive tool arguments, provider credentials or unsanitized stdout.

The current transport is Odoo polling. SSE/WebSocket is not required by the architecture; introduce streaming transport only if it improves UX without moving authority out of Odoo.

## Codex lifecycle

The current provider starts Codex App Server as a subprocess. Account lifecycle is separate from turn lifecycle: credentials live in provider-owned `CODEX_HOME`; the database only controls whether it is connected/enabled.

The UI account service refreshes while the Assistant is active/visible, with faster polling during device-code login and slower refresh while authenticated. Chat/history are not bootstrapped until authentication is usable.

## Failure classes

The runtime must distinguish at least:

- invalid model/provider output before an effect;
- unavailable/denied capability;
- ACL/record-rule/field-access denial;
- provider unavailable/timeout;
- cancellation before effect;
- failed verified effect;
- uncertain/partial effect requiring recovery;
- stale lease/restart recovery.

Do not collapse all of these into a generic assistant error when the host knows a more precise safe state.

## Product directions

The next architecture layers should compose around this runtime rather than fork it:

- Agent/Profile configuration;
- Skill/CapabilityBundle grouping/instructions;
- external-addon CapabilityProvider extension point;
- context providers and semantic metadata;
- knowledge/source retrieval with provenance;
- domain business-action packs;
- agentic evals;
- richer public progress/approval UX;
- future non-chat invocation modes using the same host.

They are not license to reintroduce rigid request routers or a second operational agent runtime.
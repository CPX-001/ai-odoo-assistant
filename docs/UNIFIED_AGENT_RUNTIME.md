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
   +--> effective CapabilityRegistry views
   +--> private durable working transcript
   +--> CodexDecisionEngine -> exactly one NextDecision
   |        final_answer
   |        reasoning_capability_call
   |        plan_step_proposal
   |
   +--> host validation / bounded dispatch
   |
   v
CapabilityExecutor + policy + approval + verification
   |
   v
persisted result/events
```

The active product composition now uses the ADR-019 one-decision Codex adapter. The previous
monolithic `CodexReasoningEngine.run_agent_turn()` remains only as a non-default rollback seam while
real-environment convergence validation is pending.

## Context

The host reconstructs context from Odoo rather than trusting browser/model assertions. Relevant context includes authenticated user, active/allowed companies, conversation, screen/model/record information and policy snapshot.

Screen/record text is context data, not permission. Retrieved or user-controlled text must never enable a capability, lower risk or grant approval.

## Reasoning vs execution

`CodexDecisionEngine` proposes exactly one next operation. `AgentTurnService` resolves and validates
that operation against the effective catalog before anything executes.

REASONING calls may execute only through `CapabilityExecutor` with
`ExecutionAuthority.REASONING`. The effective Odoo Environment remains the originating user with
`su=False`; ACLs, record rules, field access and active-company scope continue to be Odoo
authority. The provider does not receive an ORM handle and cannot turn a name in its output into a
new capability.

Every active-turn boundary is represented in a private typed transcript. Public turn events remain
a separate sanitized projection and do not receive private capability arguments/results.

## Effective capability catalog

The catalog is built per run/turn from installed definitions and context. The registry exposes reduced views for reasoning and planning instead of leaking handler internals.

Current state:

- atomic `CapabilityDefinition`: implemented;
- deterministic discovery of core provider modules: implemented;
- guards/groups/dependencies/effective filtering: implemented;
- provider-neutral adapters/views: implemented;
- strict `NextDecision` union: implemented;
- private durable active-turn working transcript: implemented;
- host-owned iterative READ dispatch: implemented;
- canonical PLAN dispatch into the action lifecycle: pending E2E-4 at this checkpoint;
- external addon `CapabilityProvider`: not yet first-class;
- configurable Skill/CapabilityBundle: not yet implemented;
- `discovered -> available -> revealed -> active` progressive disclosure: design direction, not current runtime behavior.

## Reads

The general read path remains schema-first. Query capabilities inspect models/fields visible to the
effective user, issue schema fingerprints and require bounded inputs before querying.

The execution shape is now:

```text
Codex NextDecision
 -> host validates reasoning capability + arguments
 -> persist private decision/call boundary
 -> execute REASONING capability inside the current Odoo cursor/savepoint
 -> persist bounded private result/error
 -> rebuild provider input from authoritative working items
 -> next NextDecision
 -> final_answer
```

Provider decisions, capability calls, consecutive correctable failures, per-definition calls and
transcript/result bytes are bounded. Cancellation is checked before provider and capability calls.
A persisted pending call id is never blindly executed again after restart; it is closed as an
interrupted call so the provider can decide what to do next with a new call id.

A read result is untrusted content for reasoning. It can answer the user but cannot alter policy.

## Effects

Effectful capabilities still carry explicit effect/risk/approval metadata. The authoritative
lifecycle remains:

```text
canonical proposal
 -> effective schema/preconditions
 -> prepare/preview
 -> policy decision
 -> approval when required
 -> durable write barrier
 -> execute under effective user
 -> verify
 -> receipt/public result
```

At the E2E-3 checkpoint the decision contract can parse and validate a `plan_step_proposal`, but the
active composition intentionally rejects PLAN dispatch until E2E-4 wires that proposal into the
existing lifecycle. No effect is executed during reasoning.

An approval must bind to the prepared effect/preconditions rather than act as a generic
conversational “yes”. Stale or ambiguous effects fail/recover safely instead of being replayed
blindly.

## Durable turns

Long turns are Odoo records. The browser does not hold the transaction/runtime alive.

Queue properties include:

- queued claim by cron;
- lease ownership/expiry;
- bounded attempts;
- cancellation requests;
- stale recovery;
- explicit terminal/recovery states;
- persisted events consumed by cursor/polling;
- private `working_items_payload` for active host-loop recovery.

The working transcript stores only bounded active-turn state such as user input, provider
decisions, calls, results/errors, plan boundaries and terminal answer/receipt. It is not exposed by
`browser_status()`.

For completed and approval-waiting turns, the generic turn status returns the persisted authoritative result payload to the browser. Retries are safe only for replayable work. Effectful ambiguity requires verification/recovery semantics, not unconditional retry.

## Progress events

Persisted public events are projections of host state. They may communicate classes of work such as queued/analyzing/tool activity/awaiting approval/verifying/completed/failed, but must not reveal private chain-of-thought, raw prompts, sensitive tool arguments/results, provider credentials or unsanitized stdout.

The current transport is Odoo polling. SSE/WebSocket is not required by the architecture; introduce streaming transport only if it improves UX without moving authority out of Odoo.

## Codex lifecycle

The current provider starts Codex App Server as an ephemeral subprocess for each one-decision call.
Provider thread/process state is not business durability: the next call is reconstructed from Odoo
state and the bounded private transcript.

Account lifecycle is separate from turn lifecycle: credentials live in provider-owned
`CODEX_HOME`; the database only controls whether it is connected/enabled.

The UI account service refreshes while the Assistant is active/visible, with faster polling during device-code login and slower refresh while authenticated. Chat/history are not bootstrapped until authentication is usable.

## Failure classes

The runtime distinguishes at least:

- invalid provider decision before an effect;
- schema-invalid/correctable capability arguments;
- unavailable/denied capability;
- ACL/record-rule/field-access denial;
- provider unavailable/timeout;
- cancellation before effect;
- interrupted persisted read call;
- failed verified effect;
- uncertain/partial effect requiring recovery;
- stale lease/restart recovery.

Correctable pre-effect failures may be returned privately to Codex within the bounded correction
budget. An authority/ACL denial may be followed only by a final explanation; it cannot trigger
another business capability execution in the same loop. Post-write-barrier ambiguity remains a
recovery state, never a blind retry.

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

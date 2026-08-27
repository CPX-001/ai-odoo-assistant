# E2E agent-loop convergence: Apexive behavior, Assistant authority

Research date: 2026-08-27
Assistant baseline inspected: `4b5d510e6f8a61e9d2378b0bb00c678f95b67b4e`
Apexive `odoo-llm` baseline inspected: `609ec6dda3645165f6a4a843d7af5d286081a29d`
Status: proposed execution architecture; not current-state authority

## Executive decision

Keep the existing Assistant product, UI, durable Odoo turns, effective-user authority,
capability registry, previews, approvals, write barrier and verification. Replace only the fragile
provider orchestration contract with the mature control-loop pattern demonstrated by Apexive:

```text
model selects one next operation
-> host validates and executes it
-> host appends a typed result
-> model sees that result and selects the next operation
-> repeat until a final answer or an authoritative action proposal exists
```

This is a convergence, not an Apexive port. Apexive supplies the proven loop shape. The Assistant
continues to own security, persistence, policy and the user experience.

The current Phase 0 ACTION blocker is no longer best treated as a prompt-tuning problem. The real
run at `5995717` exposed six reasoning and six planning capabilities, but Codex emitted no tool
call, no staged step and a low-confidence read-only final answer. The first missing boundary was
`plan_step_staged`; preview, approval and execution were never reached. Another instruction-only
patch would repeat the same architectural bet.

## Evidence and diagnosis

### What Apexive gets right

`llm_assistant/models/llm_thread.py` implements a small, explicit host loop. An assistant tool call
is persisted, the host executes it, a tool-result message is persisted, and the provider is called
again with the chronological transcript. The loop ends only when the assistant returns content
without another tool call.

The local `llm_codex` adapter further reduces protocol risk. It does not depend on App Server
dynamic tools for its core decision. It sends the effective catalog as data and requires a
structured result that selects either one tool plus JSON arguments or final content. The Apexive
host then performs the selected call and starts the next model decision.

That design has three practical advantages:

1. every provider decision has one meaning;
2. every tool result is explicit input to the next decision;
3. a failed call can be returned as structured evidence for bounded self-correction.

### What the Assistant already does better

The Assistant must not replace these existing properties with Apexive equivalents:

- Odoo is the durable authority for turns and state;
- execution uses the originating effective user with `su=False`;
- tools come from one typed `CapabilityDefinition` registry;
- schemas, enablement, ACLs, policies and budgets are host-owned;
- PLAN capabilities cannot execute during reasoning;
- writes follow prepare, preview, policy/approval, durable barrier, execute and verify;
- uncertain post-barrier outcomes fail into recovery rather than blind retry;
- browser payloads and diagnostics are bounded and redacted.

Apexive's direct mail-message loop, provider-level `sudo`, raw result/error propagation and generic
tool execution are reference behavior only. They are not safe code to transplant.

### Why the current Assistant loop fails

The important defects are architectural and ordered by impact.

#### 1. The provider owns too much of one turn

`CodexReasoningEngine.run_agent_turn()` asks one App Server turn to discover data, invoke multiple
dynamic tools, stage writes and finally emit the complete `AgentReasoningResult`. The host can
service dynamic tool callbacks, but it does not own an outer decision loop. A plausible final
answer can therefore terminate the whole turn before the required action boundary is crossed.

#### 2. ACTION has had two representations

The initial contract required Codex to call a stage-only PLAN tool and also reproduce the plan in
the final structured `plan` array. The v2 fallback correctly made one staged candidate sufficient,
but the real run showed that Codex may skip staging entirely. The canonical action proposal must
be one host-observed provider decision, not a side effect plus a second final serialization.

#### 3. Working context is flattened

`_conversation_summary()` converts the recent conversation to bounded `User:` / `Assistant:`
strings. It does not preserve typed tool calls, tool results, plan candidates or recoverable tool
errors. The model cannot reliably distinguish user statements from authoritative Odoo facts and
cannot continue a durable multi-step operation after a host boundary.

#### 4. Tool errors cannot drive a normal correction cycle

Capability failures are strongly normalized, but the monolithic turn has no provider-neutral
working transcript controlled by Odoo. The desired behavior is: persist a safe error result,
decrement the retry budget, and ask for the next decision. Fatal policy/authority failures remain
terminal; correctable schema/argument failures may be repaired within bounds.

#### 5. App Server compatibility is coupled to product semantics

The adapter's strict notification allow-list can fail a valid product turn when App Server adds an
unimportant event. Protocol conformance and the business decision contract need separate tests and
failure codes. Unknown notifications may be ignored only when they cannot alter item, tool,
approval, completion or error semantics.

#### 6. Completion after a write loses conversational quality

After verified execution, `_completion_answer()` replaces the model's response with a generic host
receipt. That is safe, but it prevents a natural answer grounded in the verified effect. A later
bounded synthesis decision may turn the verified receipt into conversational text; the receipt
remains the authority.

## Side-by-side disposition

| Concern | Apexive | Current Assistant | Target |
| --- | --- | --- | --- |
| UI and product intent | Generic thread UI | Preferred custom panel | Keep Assistant unchanged |
| Orchestration | Host loop over one tool decision | One monolithic provider turn | Adopt host loop |
| Tool transcript | Typed assistant/tool messages | Mostly in-process callbacks | Persist typed working items |
| Tool selection | Structured one-tool result in `llm_codex` | App Server dynamic tools plus final plan | Structured next-decision contract first |
| Tool authority | Generic tool model | Typed capability registry | Keep Assistant registry/executor |
| Write safety | Tool-specific behavior | Preview/approval/barrier/verify | Keep Assistant lifecycle |
| User authority | Can use broad provider execution | Effective Odoo user, `su=False` | Keep Assistant authority |
| Recovery | Loop/error message oriented | Durable pre/post-barrier semantics | Keep Assistant recovery, add bounded correction |
| History | Chronological roles and tool results | Flattened summary | Typed bounded transcript |

## Target E2E flow

```text
Browser submit
  -> Odoo persists user message and queued turn
  -> cron leases turn under the originating user
  -> Odoo resolves the effective capability catalog
  -> Odoo builds a typed working transcript
  -> Codex returns exactly one NextDecision
       FINAL_ANSWER
       CALL_REASONING_CAPABILITY
       PROPOSE_PLAN_STEP
  -> Odoo validates the decision against the effective catalog

CALL_REASONING_CAPABILITY
  -> execute with REASONING authority
  -> persist redacted call/result working items
  -> append typed result to model input
  -> request next decision

PROPOSE_PLAN_STEP
  -> validate and bind the PLAN capability; do not execute it
  -> this host-observed proposal is the canonical plan step
  -> prepare authoritative preview and preconditions
  -> if confirmation is required, persist awaiting_confirmation
  -> after one approval, re-lease the same bound plan
  -> durable write barrier -> execute -> verify
  -> persist authoritative receipt
  -> optionally request one bounded final synthesis from Codex

FINAL_ANSWER
  -> allowed when no unresolved provider call or plan proposal exists
  -> persist assistant message and complete turn
```

The model decides what it wants to do; the host decides whether that decision is valid and whether
it may have an effect. Those responsibilities must never be merged.

## Provider-neutral decision contract

The first implementation should use one strict union returned by Codex structured output:

```text
NextDecision =
  FinalAnswer {
    kind: "final_answer",
    answer: string,
    confidence: high | medium | low
  }
  | ReasoningCapabilityCall {
    kind: "reasoning_capability_call",
    call_id: string,
    capability: string,
    arguments: object
  }
  | PlanStepProposal {
    kind: "plan_step_proposal",
    call_id: string,
    capability: string,
    arguments: object,
    user_summary: string
  }
```

Rules:

- exactly one branch per provider decision;
- a PLAN proposal is canonical when the host validates and stages it;
- do not require the same step in a later `plan=[]` field;
- `FinalAnswer` never carries executable instructions;
- capability names and arguments are untrusted until resolved and validated by the host;
- capability results are host-produced typed items, never model claims;
- explicit requested mutations must select a PLAN proposal when an effective supported capability
  exists; representative evals enforce this behavior without a regex intent router;
- unsupported or forbidden mutations produce an honest final answer or structured host failure,
  never a fabricated success.

Use the entire effective catalog for now, as requested. “Entire” means every enabled definition
visible to the effective user: REASONING definitions may be called, PLAN definitions may only be
proposed. It never means disabled capabilities, inaccessible models, arbitrary ORM methods, SQL,
Python, shell or `sudo`.

## Durable working transcript

Introduce an Odoo-owned typed record or strictly validated JSON list bound to the durable turn. A
working item has a monotonic sequence and one of these types:

- `user_input`;
- `assistant_decision`;
- `capability_call`;
- `capability_result`;
- `capability_error`;
- `plan_step_proposed`;
- `plan_prepared`;
- `verified_effect_receipt`;
- `final_answer`.

Persist only the minimum required for recovery and auditing. Public events remain a separate,
redacted projection. Provider input may contain bounded capability results needed for reasoning;
browser status and diagnostics must not expose them automatically.

Every provider call is rebuilt from:

1. system/developer instructions;
2. current user request and bounded typed conversation history;
3. fresh screen context;
4. effective capability catalog and schemas;
5. bounded working items for the active turn;
6. remaining budgets.

Do not flatten tool roles into prose and do not treat old screen context as fresh authority.

## Bounds, transactions and recovery

The host loop must be finite and restartable:

- maximum provider decisions per turn;
- maximum capability calls per turn and per definition;
- maximum consecutive correctable failures;
- maximum total transcript bytes and per-result bytes;
- one unique `call_id` per decision;
- no duplicate execution for a persisted completed `call_id`;
- cancellation and lease checks before provider calls and capability calls;
- transaction/savepoint boundaries around read calls;
- the existing durable write barrier immediately before the first effect;
- no automatic retry after an ambiguous post-barrier failure.

On worker restart, Odoo reconstructs the next safe state from persisted working items and the plan
envelope. Provider thread state may be discarded; business execution state may not.

## Ordered implementation slices

### E2E-0 — Freeze behavior and contracts

Add table-driven eval fixtures for hello, schema-backed read, multi-read synthesis, supported patch,
supported create, validation repair, access denial and unsupported action. Capture expected
decision sequences, not prose wording.

Exit gate: current deterministic tests remain green and every fixture has an explicit maximum
decision/call budget.

### E2E-1 — Introduce `NextDecision` without changing the UI

Add the provider-neutral union and a Codex structured-output adapter based on the working local
`llm_codex` selection pattern. Keep the current adapter behind a conformance comparison until the
new route covers hello and READ.

Exit gate: Codex returns one validated decision; unknown capability, invalid arguments and invalid
union branches fail with stable codes and no capability execution.

### E2E-2 — Persist the typed working transcript

Add the Odoo-owned working items and projections. Migrate active-turn orchestration only; do not
rewrite historical chat storage or the panel.

Exit gate: a worker restart between call and result cannot duplicate the call, and tool results are
available to the next decision without appearing in the public answer/event feed.

### E2E-3 — Move READ to the host loop

Implement `next decision -> execute reasoning capability -> append result -> next decision`. Return
safe correctable errors to Codex within the existing budgets.

Exit gate: the real hello and READ baselines pass; a multi-step read uses authoritative results and
terminates without infinite calls.

### E2E-4 — Make PLAN proposal canonical

Route `PlanStepProposal` directly into the existing `CapabilityPlanService.prepare`. Delete the
dual staged-tool/final-plan obligation after parity tests pass. Keep all current approval,
revalidation, barrier, execution, verification and recovery code.

Exit gate: the disposable real ACTION reaches an exact preview with the record unchanged, one
approval causes exactly one verified effect, and the fixture is restored.

### E2E-5 — Verified completion synthesis

Optionally call Codex once after verified execution with a bounded authoritative receipt. If
synthesis fails, retain the deterministic completion answer.

Exit gate: no model output can alter effect or verification state, and the answer never claims an
unverified effect.

### E2E-6 — Protocol hardening and cleanup

Generate/pin App Server schemas for the installed Codex version, classify additive notifications,
remove the superseded monolithic path and document rollback.

Exit gate: conformance fixtures cover supported protocol events, unknown harmless events, unknown
semantic events, timeout, EOF, auth, invalid output and cancellation.

## File-level implementation map

| Area | Expected change |
| --- | --- |
| `runtime/agent/contracts.py` | Add `NextDecision` union and working-item contracts. |
| `runtime/agent/codex.py` | Implement one-decision structured Codex call; isolate App Server transport. |
| `runtime/agent/service.py` | Own the bounded outer loop and decision dispatch. |
| `runtime/agent/plan.py` | Accept canonical validated proposals; retain preparation/execution semantics. |
| `models/embedded_runtime.py` | Persist/resume working items and compose the existing authoritative services. |
| `models/chat_storage.py` or a new focused model | Store typed active-turn working items without changing public chat messages. |
| `runtime/capabilities/*` | Reuse; only add projections/helpers required by the decision contract. |
| `controllers/*` and `static/src/*` | No planned interface redesign in these slices. |
| tests | Add contract, restart/idempotency, loop, real READ and real ACTION coverage. |

## Roadmap correction

The previous roadmap prohibited Phase 1 provider/runtime work until the existing ACTION gate
passed. Evidence now disproves the assumption that ACTION can be closed by another bounded prompt
correction inside the monolithic turn. A narrow orchestration slice is therefore permitted inside
Phase 0 solely to close the hard ACTION gate.

This permission does not unlock streaming redesign, provider expansion, RAG, tool-picker UX or
general refactoring. The active order is E2E-0 through E2E-4, followed by the existing real ACTION
and aggregate Phase 0 gates. Later roadmap phases remain locked.

## Non-goals

- no visual redesign or tool selector work;
- no OpenAI API key/provider implementation;
- no Apexive mail-thread or ORM tool migration;
- no arbitrary model/method execution;
- no natural-language regex router for write intent;
- no weakening of ACLs, record rules, approval or verification;
- no claim that App Server process/thread persistence is business durability;
- no broad RAG work before the core loop passes its gates.

## Required ADR

Before E2E-2 or the removal of the existing monolithic provider path, add an ADR accepting the
host-owned iterative decision loop and canonical plan proposal. The ADR must explicitly preserve
ADR-016/ADR-017 authority invariants and describe rollback. Research documentation alone does not
authorize a production architecture change.

## External validation basis

The official Codex App Server lifecycle is initialize, thread start/resume, turn start, streamed
item/turn events and turn completion. It exposes thread, turn and item primitives and supports
version-specific schema generation. The target above uses that transport while keeping Odoo as
business authority. The implementation prompt should remain lean, give tools precise descriptions,
and be evaluated on representative multi-step tasks rather than prose compliance alone.

References:

- Codex App Server: https://developers.openai.com/codex/app-server
- OpenAI model/prompt guidance: https://developers.openai.com/api/docs/guides/latest-model

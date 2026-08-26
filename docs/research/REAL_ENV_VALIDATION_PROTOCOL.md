# Real Odoo + Codex validation protocol

Inspected main: `b6a7b77bc91b7e80b25551d0c07334d396f68083`  
Date: 2026-08-26  
Status: validation guidance

## Purpose

Some roadmap gates cannot be proven from unit tests or repository inspection. They require the actual supported product path:

```text
browser / Odoo RPC
  -> Odoo 18 Community
  -> persisted turn + cron worker
  -> embedded runtime
  -> configured Codex App Server
  -> capabilities under the real user Environment
  -> browser-visible result/activity/error
```

This document standardizes those checks so a phase is not closed because `it worked once` or because an AI coding session could not access the real deployment.

## Environment assumptions

Unless a validation says otherwise:

- Odoo 18 Community;
- the addon installed/updated from the exact commit being tested;
- normal embedded runtime, not the retired sidecar;
- Codex executable/auth configured through the supported product path;
- at least one administrator/internal user;
- at least one limited-permission internal user for ACL tests;
- cron processing enabled;
- representative demo/test records for `res.partner` and, where installed, Sales/CRM.

Record the actual Odoo and Codex versions in validation evidence.

## Safety rules

Use disposable/demo records for mutation tests whenever possible.

Never run destructive or financially meaningful actions merely to satisfy a roadmap gate. If a test requires an effect, prefer a reversible low-risk field change or explicitly prepared demo record.

Never commit:

- passwords/tokens/auth files;
- raw prompts containing sensitive business data;
- complete stdout/stderr from provider processes;
- unrestricted tool arguments/results;
- customer data not specifically required for sanitized evidence.

## Evidence record

Every manual/live validation should record:

```text
validation_id:
commit_tested:
date:
odoo_version:
codex_version:
user_profile: admin | limited | other
result: PASS | FAIL | BLOCKED
observed:
expected:
latency_or_counts:
artifact_refs:
notes:
```

Evidence may live in a phase record, a sanitized JSON report produced by test tooling, or a dedicated validation note. The exact format is secondary; the validation ID and commit tested are mandatory.

## Phase 0 — reproducible baseline

Phase 0 already has executable capture tooling in `tests/e2e/phase0_live_capture.py` and the gate evaluator in `tests/e2e/phase0_report.py`. Use those scripts where possible instead of manually transcribing backend timings.

### P0-REAL-HELLO

Purpose: establish simple-turn baseline.

Procedure:

1. ensure Codex is authenticated;
2. open the Assistant in a neutral Odoo screen;
3. send a trivial greeting such as `Hola`;
4. run/capture the matching `hello` scenario;
5. record final latency and provider timing decomposition.

Pass:

- request completes normally;
- no capability is required merely to answer a greeting;
- no protocol/runtime error;
- timings are captured sufficiently to attribute the delay.

Repeat enough times to obtain a useful latency distribution; do not use one warm run as the baseline.

### P0-REAL-READ

Purpose: prove a normal capability-backed read.

Procedure:

1. use a known demo partner;
2. ask the Assistant to find/read a small number of non-sensitive fields;
3. capture the `read_partner` scenario;
4. inspect `tool.started`/completion evidence and final answer.

Pass:

- the expected bounded query path executes;
- result reflects real Odoo data;
- timing decomposition includes queue/provider/tool/finalization.

### P0-REAL-ACTION

Purpose: establish one end-to-end safe write/approval baseline.

Procedure:

1. prepare a disposable demo partner;
2. request a harmless reversible field update;
3. inspect preview;
4. approve through the product UI when required;
5. verify the record after execution.

Pass:

- preview matches intended change;
- approval is required according to current policy;
- effect occurs once;
- verification confirms the resulting state;
- no blind retry is needed.

### P0-REAL-FAILURE-PAIR-*

Phase 0 needs at least five distinct original-error vs final-UI-error pairs. Use controlled fixtures for:

- `provider_auth_missing`;
- `provider_process_missing`;
- provider disconnect/EOF where safely injectable;
- provider timeout;
- invalid provider/capability output;
- optionally ACL denial/cancellation/recovery as extra coverage.

Pass:

- original sanitized code is known;
- final UI code/category is observed rather than guessed;
- five distinct failure paths are represented.

## Phase 1 — provider boundary and Codex compatibility

### P1-REAL-SOAK-100

Purpose: prove the provider boundary is no longer fragile under normal repeated use.

Run at least 100 turns composed of trivial greetings and simple reads on the exact supported Codex/runtime version.

Capture:

- completion count;
- protocol-shape failures;
- provider process failures;
- median/p95 latency;
- unexpected retries;
- any unknown-notification diagnostics.

Pass:

```text
protocol-shape failures = 0
host-authority bypasses = 0
wrong-turn/call binding = 0
```

Ordinary model/content failures should be classified separately; they are not automatically protocol regressions.

### P1-REAL-TOOLCALL

Purpose: prove dynamic tools still execute through the host after provider refactor.

Procedure:

- trigger one schema/query capability;
- verify the model's request is mapped to the expected logical capability;
- verify Odoo ACL/user context is preserved;
- ensure no provider-specific direct ORM path exists.

### P1-REAL-CANCEL

Purpose: prove cancellation binds to the correct active provider turn.

Procedure:

- start a deliberately slow but safe read-only request;
- cancel via supported UI/path while running;
- observe terminal state and provider interruption.

Pass:

- only the intended turn is cancelled;
- no business effect occurs after cancellation;
- subsequent turns remain healthy.

### P1-REAL-VERSION

Record the exact Codex version used by the supported integration and verify startup/initialize/turn/tool streaming against it. If the product chooses a pinned SDK/runtime pair, validate that exact pair rather than whatever `latest` happens to be installed.

## Phase 2 — failure contract

For every major failure family added to the failure taxonomy, define at least one real presentation test.

Minimum set:

### P2-REAL-AUTH

Disconnect/disable the supported Codex account and submit a request.

Pass: UI communicates provider/auth setup problem; it must not report an unrelated data/tool/context error.

### P2-REAL-ACL

Use the limited user to request inaccessible data.

Pass: access/policy category survives to UI without leaking the inaccessible data or implying Codex is broken.

### P2-REAL-TIMEOUT

Use the controlled timeout fixture.

Pass: timeout category and retry guidance match the actual safety state; a possible write is never declared absent merely because the provider timed out.

### P2-REAL-TOOLFAIL

Trigger a controlled capability failure.

Pass: tool/execution category survives independently from provider connectivity.

### P2-REAL-RECOVERY

Exercise or simulate the documented `recovery_required` write-barrier path on disposable data.

Pass: UI says the result is uncertain/requires verification and does not encourage a blind repeat.

## Phase 3 — public activity

### P3-REAL-ACTIVITY-READ

Ask for a known partner or sales record.

Pass:

- latest visible activity reflects the actual operation, e.g. model/schema/query information when safe;
- it is visually distinct from Assistant answer text;
- expandable history shows ordered public activity events;
- no private reasoning is displayed.

### P3-REAL-ACTIVITY-ACTION

Request a safe write requiring preview/approval.

Pass should visibly distinguish stages such as:

```text
preparing/previewing
awaiting approval
executing
verifying
completed
```

Where validated record/model information is safe, the UI should be specific enough to be useful rather than only `processing`.

### P3-REAL-LIVE-VISIBILITY

Purpose: prove events are visible while the worker transaction is still running.

Use a safe capability that lasts long enough to observe intermediate states.

Pass: at least one meaningful capability/public activity event becomes browser-visible before final completion. If not, investigate transaction visibility; do not fake liveness with local hard-coded timers.

### P3-REAL-REDACTION

Inspect the activity history for tool calls involving identifiers/filters.

Pass: no credentials, raw prompts, provider stdout/stderr, private chain-of-thought or sensitive unrestricted arguments are exposed.

## Phase 4 — real answer streaming

### P4-REAL-FIRST-DELTA

Ask for a response long enough to stream.

Pass:

- answer text begins before the final result is available;
- `browser_first_answer_delta` is measurable;
- activity events are not concatenated into answer text.

### P4-REAL-FINAL-PARITY

Capture the streamed text and authoritative final answer.

Pass: final rendered answer matches the authoritative response contract after any documented normalization. No duplicated prefixes/suffixes or lost chunks.

### P4-REAL-CANCEL-STREAM

Cancel a read-only request during answer streaming.

Pass: stream terminates cleanly and does not later append a stale final answer into a different/current conversation.

### P4-REAL-UTF8-FRAGMENT

Exercise Spanish/non-ASCII text and fragmented deltas.

Pass: no malformed Unicode or duplicate/truncated characters.

## Phase 5 — chat UX

### P5-REAL-CHAT-BASIC

Validate desktop panel behavior for:

- user message appears immediately;
- activity occupies activity surface, not Assistant bubble;
- answer streams/renders in answer surface;
- final message persists in history;
- new conversation works.

### P5-REAL-ERROR-UX

Run representative failures from Phase 2.

Pass: wording is useful and context-specific while remaining grounded in structured failure facts. AI-generated friendly wording, if used, must not alter the authoritative category/remediation facts.

### P5-REAL-APPROVAL-UX

Request one safe action.

Pass: preview clearly communicates intended effect, affected record(s), risk and approval; verification result is visible afterwards.

### P5-REAL-RECOVERY-UX

Pass: ambiguous effect state is clearly different from normal failure and normal completion.

## Phase 6 — measured latency optimization

Real tests here depend on the bottleneck found in Phase 0.

Always rerun at least:

- greeting distribution;
- simple read distribution;
- one action distribution;
- provider startup timings;
- time to first useful activity;
- time to first answer delta;
- final completion time.

Pass criteria must be stated before each optimization slice. Do not accept a latency win that regresses tool choice, permissions, write safety or recovery.

If a warm/reusable Codex App Server is proposed, require an ADR plus real tests for isolation, stale state, restart, auth changes, concurrency and cancellation before replacing ephemeral-per-turn semantics.

## Phase 7 — regression/eval gates

Real agentic evals should cover at minimum:

- greeting/general response;
- schema/model discovery;
- bounded record query;
- aggregation;
- HOW_TO grounded in actual installation when possible;
- ACL denial;
- action preview/approval/verify;
- provider error;
- cancellation/recovery;
- custom-addon/source diagnosis when those capabilities are active.

Repeat probabilistic cases enough times to distinguish a stable regression from one unlucky generation. Grade outcomes/invariants, not an exact tool-call sequence when several valid paths exist.

## Phase 8 — capability mini-framework

When Provider/Bundle/Skill layers are introduced, real tests must prove composition does not change authority.

Minimum live checks:

### P8-REAL-PROVIDER-DISCOVERY

Install/enable one trusted test extension provider.

Pass: its capability appears when expected and disappears cleanly when disabled/uninstalled; core catalog remains usable if the extension is unavailable.

### P8-REAL-BUNDLE-ACTIVATION

Use two different contexts/profiles where a bundle should be available in one and not the other.

Pass: effective catalog changes as specified without changing Odoo permissions.

### P8-REAL-AUTHORITY

A capability hidden/disabled by host configuration remains unavailable even if the user explicitly asks the model to call it.

### P8-REAL-DISCLOSURE

If progressive disclosure is implemented, compare eval quality/latency/tool-selection before and after. Do not keep it merely because it reduces token count.

## Phase 9 — RAG/domain expansion

Every new retrieval or domain capability must add its own real validation IDs.

For retrieval:

- provenance/citations;
- ACL/source access;
- freshness/reindex behavior;
- exact-vs-semantic retrieval;
- indirect prompt injection from retrieved content;
- no retrieval text becoming authority.

For business actions:

- eligibility;
- preview;
- approval policy;
- exactly-once/idempotency behavior where applicable;
- verification;
- recovery after interruption.

## Validation stop rule

A roadmap run may prepare scripts/fixtures for a real validation, but **must not mark the validation PASS unless the exact commit was actually tested in a real Odoo+Codex environment**.

If a later implementation commit changes the subsystem under test materially, repeat the affected validation IDs. Evidence from an older commit is historical evidence, not proof of the new one.
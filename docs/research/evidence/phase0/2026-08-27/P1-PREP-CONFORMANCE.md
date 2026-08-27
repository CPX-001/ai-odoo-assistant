# P1-PREP-CONFORMANCE — adapter-neutral conformance contract

Date: 2026-08-27  
Inspected HEAD: `c7ea9dbaba2cc0305ff0f3af2a34c8a3e9f7a829`  
Status: `COMPLETE` (look-ahead preparation only)

## Objective

Use the explicitly authorized Phase 1 preparation lane while P0.3 waits on real Odoo+Codex evidence.
This slice prepares an adapter-neutral conformance contract without changing the current
`CodexReasoningEngine`, provider lifecycle, Odoo authority, capability execution, writes, recovery,
or browser behavior.

## Repository findings

Current `addons/odoo_ai_assistant/runtime/agent/codex.py` still:

- starts one ephemeral App Server per turn;
- requests `approvalPolicy=never`;
- uses `sandbox=read-only`;
- exposes no runtime workspace roots;
- passes dynamic tools while keeping execution in the host `CapabilityExecutor`;
- validates thread/turn/call identity and fails closed on mismatches;
- currently rejects unknown notifications outside its explicit allowlist.

The last point is exactly why Phase 1 needs conformance tests before changing compatibility policy.
This slice does not alter that policy.

## Added contract/harness

Files:

- `tests/fixtures/codex_provider_conformance_cases.json`
- `tests/contracts/codex_provider_conformance.py`
- `tests/unit/test_codex_provider_conformance.py`

The manifest contains exactly the fourteen cases required by the Phase 1 playbook:

1. initialize;
2. thread isolation;
3. turn output schema;
4. agent-message delta;
5. completed agent message;
6. dynamic-tool mapping;
7. capability success;
8. capability failure;
9. unknown benign notification;
10. malformed critical event;
11. identity mismatch;
12. cancellation;
13. terminal provider failure;
14. overload/backpressure.

The harness is adapter-neutral. A future current-custom-adapter binding and an experimental
`openai-codex` binding can both implement the same small `observe(case)` protocol and produce
sanitized observations. The evaluator requires both the expected outcome and every named safety
assertion.

No fixture contains business data, credentials, raw provider output, prompts, tool results, or
private reasoning.

## Deterministic validation

Actually executed against the exact new files before publication:

```text
python -m py_compile tests/contracts/codex_provider_conformance.py
PASS

python -m pytest -q tests/unit/test_codex_provider_conformance.py
4 passed in 0.07s
```

The tests prove:

- the manifest contains exactly all required Phase 1 cases;
- missing isolation/safety assertions fail the evaluator;
- the same harness can execute an arbitrary adapter implementation;
- incomplete manifests are rejected.

This is preparation only. It does **not** claim that the current custom adapter passes the
conformance suite, and no official SDK adapter has been tested.

## Look-ahead accounting

This consumes the final currently available look-ahead slot while `VD-P0.3-REAL` remains open.
No additional speculative implementation should start until the P0.3 real gate is processed.

## Exact next action

Return to Phase 0 and run `P0.3-REAL-READONLY-CRASH-PROBE` on current `main`. Do not bind or change
the production provider contract yet. If P0.3 passes, proceed to the normal P0.4 fault-injection
slice. If it fails, create the smallest P0.3 corrective child slice first.

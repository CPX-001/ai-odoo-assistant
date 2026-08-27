# P0-REAL-ACTION — zero-step regression gate

Date: 2026-08-27  
Inspected HEAD: `0d281785eb60f6c6210a8e247adac1f8aa287535`  
Status: `CORRECTION_LOCAL_VALIDATION_COMPLETE`

## Processed real evidence

The real ACTION attempt at `38c7c9a121cc797b9a2737fb312283506aa152f6` failed before approval: the persisted turn completed after three bounded tool pairs with no error, no write barrier and `plan_step_count=0`. No approval preview appeared and the disposable record remained unchanged.

## Diagnosis boundary

Static inspection of the current provider-neutral agent and Codex adapter establishes an acceptance gap, not a claim about hidden model reasoning:

- `AgentReasoningResult.plan` defaults to an empty tuple;
- `AgentTurnService._validate_plan()` accepts an empty plan whenever the host write-step budget permits zero or more steps;
- the Codex final-output schema requires a `plan` array but has no `minItems`;
- base instructions tell the model to add a plan capability when required, but the host has no independent semantic signal proving that a particular natural-language request required a write.

Therefore a syntactically valid `plan=[]` can currently become a normal completed read-only turn even when real-environment evidence shows the user's requested supported mutation was omitted.

This does **not** justify adding a regex/router that guesses write intent, weakening approval, or making a model-produced label authoritative.

## Implemented regression/eval

Added `tests/e2e/phase0_action_acceptance.py` and `tests/unit/test_phase0_action_acceptance.py`.

The evaluator consumes only sanitized evidence and requires an explicit external classification `request_kind=explicit_supported_write`. For that evidence class it rejects zero/missing action steps, missing approval preview, absence of proof that the record remained unchanged before approval, invalid turn/plan states or a terminal error.

It does not inspect prompt text, provider output, tool arguments/results, business values or private reasoning. It does not execute or approve a write.

## Deterministic validation actually executed

Against the exact evaluator/test contents in an isolated executable tree:

```text
python -m py_compile tests/e2e/phase0_action_acceptance.py
PASS

python -m pytest -q tests/unit/test_phase0_action_acceptance.py
3 passed in 0.06s
```

The host emitted unrelated `artifact_tool` spreadsheet warmup diagnostics on stderr; both commands returned exit status 0.

Covered regressions:

1. `completed + plan_step_count=0 + no preview` is rejected;
2. a supported write stopped at a required preview is accepted;
3. a preview is rejected if unchanged pre-approval state is not proven.

## Consequence

The observed zero-step result now has a deterministic acceptance regression, but product runtime behavior is intentionally unchanged. `P0-REAL-ACTION` remains HARD/BLOCKED.

The next corrective slice must identify the smallest provider/agent-contract correction that makes an explicit supported mutation reliably produce a bounded planning capability without reintroducing workflow routing or moving authority out of Odoo. That correction must then pass deterministic tests and a new disposable real ACTION attempt.

## Subsequent correction validation

The planning-obligation correction at `075138d7d9b519d46c60990ad465f06832d0bae8`
was locally validated in an Odoo-capable environment. Validation first found that the new Odoo
test was not imported and therefore was not being discovered; checkpoint
`08564a9f93ebd890dc7238db91ab9f6d191b2502` registers it and fixes two test-only assumptions found
once it actually executed.

```text
standalone Phase 0/provider suite: 39 passed
Odoo planning/action/revalidation: 9 passed, 0 failed, 0 errors
Odoo embedded runtime/framework/batch: 20 passed, 0 failed, 0 errors
```

The local validation debt is closed. The corrected real browser ACTION remains a hard gate.

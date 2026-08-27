# P0-REAL-ACTION v2 — sanitized capability-trace gap

Date: 2026-08-27  
Inspected HEAD: `214df5893731b7e0da2a605fa514f9c5a8328fd3`  
Status: `DIAGNOSIS_EVIDENCE_REQUIRED`

## Observed real result

The corrected real ACTION at `97617fefe40c22803a140b03023fd0df67594be1` still completed with `plan_step_count=0` after exactly three successful bounded capability pairs. No preview, approval, effect or verification occurred.

The currently committed sanitized evidence records only the counts of those tool events. It does not record which capabilities were invoked.

## Static inspection

Current `CapabilityExecutor.execute()` already emits content-free capability identity in every reasoning event:

```text
tool.started   payload={"capability": definition.name}
tool.completed payload={"capability": definition.name}
```

The live Phase 0 sanitizer in `tests/e2e/phase0_live_capture.py`, however, deliberately drops event payloads for normal tool events and preserves a payload only for `diagnostic.timing`. Therefore the repository evidence cannot distinguish, for example, whether the three successful calls included `odoo.get_effective_write_schema` or were only read/discovery calls.

This is now the material diagnosis boundary. The second correction must not be chosen from tool-count evidence alone because two different failure classes remain possible:

1. the provider never invokes the bounded write-schema preparation capability before finalizing; or
2. it does invoke the required write preparation but still omits the matching PLAN capability from the final result.

Those cases require different corrections.

## Required evidence before v2 implementation

Recover the capability-name sequence from the already persisted failed turn if it still exists in the real Odoo database. Do not record arguments, results, prompt text, assistant answer, business values, credentials or private reasoning.

Acceptable sanitized evidence shape:

```json
{
  "tool_sequence": [
    "odoo.some_read_capability",
    "odoo.some_other_read_capability"
  ],
  "plan_step_count": 0,
  "turn_state": "completed"
}
```

Capability names are trusted installed-code identifiers and are sufficient to select the next bounded correction.

## Gate consequence

`P0-REAL-ACTION-plan-omission-correction-v2` remains HARD/BLOCKED. Do not rerun the same browser mutation merely to reproduce the same outcome and do not implement another prompt-only correction until the existing failed turn's capability sequence is recovered or proven unavailable.

If the persisted events are unavailable, the next coherent implementation slice is to extend the Phase 0 sanitizer so tool events may preserve only a validated `payload.capability` identifier, add deterministic sanitizer tests, and then perform one new diagnostic ACTION capture under the same disposable safety procedure. That diagnostic capture is evidence gathering; any subsequent runtime correction still requires its own local and real validation.

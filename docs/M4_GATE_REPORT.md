# M4 gate report

Fecha: 2026-08-22.

| Check | Resultado | Evidencia/comando |
| --- | --- | --- |
| pytest/lint/mypy | PASS | `m1_gate.sh quality`: 308 passed, 8 skipped; Ruff y mypy verdes con Assistant DB real. |
| migrations/addon | PASS | Alembic fresh/upgrade/idempotencia; M4 no añade migraciones sobre el head M3. Odoo install y update: 25 tests, 0 fallos/errores cada uno. |
| M1-M3 regressions | PASS | Perfiles M1 postgres/runtime/systemd/odoo/alternate: 1 passed cada uno. Contratos M2 y E2E M3 incluidos en quality; el browser M4 revalida frontera y ACL M2, y rescan/logs M3. |
| Codex real handshake | PASS | Codex CLI 0.149.0: handshake, turn estructurado y dynamic tool smoke reales, 3 passed. |
| structured output | PASS | `AnswerEnvelope` schema + validaciones de workflow, refs y action; malformed/unknown fallan cerrado. |
| ToolExecutor budgets | PASS | Allowlist, schema, llamadas/bytes/deadline, duplicados y presupuesto insuficiente cubiertos por suite/security. |
| source dynamic tools | PASS | E2E real: `find_model_extensions` ×1, `find_symbol` ×2, `read_excerpt` ×2. |
| evidence/citations | PASS | Citas exactas a `sale.order #1/S00001` y source líneas 1-28 con fingerprint vigente. |
| security/injection | PASS | 16 tests M4 security; sin shell/SQL Odoo/método genérico, canaries ni paths físicos en browser/traces. |
| browser boundary | PASS | Chromium → Odoo únicamente; ACL negativa `access_denied`; render con `t-esc`. |
| sale.order Codex E2E | PASS | Runner real comprobó explicación causal y una `project.task` creada por el fixture. |
| FULLY_READY/degraded | PASS | Runtime operativo: `FULLY_READY`; ejecutable Codex ausente: `DEGRADED` + error UI controlado. |

## Decisión

La arquitectura conserva Odoo como autoridad de identidad/ACL, el Assistant
como autoridad de tools/evidence y Codex como adapter sustituible. No hay
imports Codex en `application`, memoria de producto en threads ni capacidades
de M5/M6. Los eventos App Server aceptados están enumerados y acotados; eventos
desconocidos fallan cerrado. El protocolo `dynamicTools` sigue siendo
experimental y queda aislado en el adapter.

**M4 GATE: PASS**

# M4 EXPLAIN workflow and Odoo presentation boundary

Fecha de verificación: 2026-08-22.

## Flujo implementado en M4-05/M4-06

```text
browser: message + ScreenContext
    -> Odoo bridge: usuario interno + identidad efectiva + delegación
    -> POST /v1/turns/explain con machine auth
    -> validación M2 compartida
    -> OdooGateway por turn
    -> fields_get + relectura ORM exacta del current record
    -> Evidence(record, checked) en ContextPack.live_evidence
    -> ReasoningEngine con workflow_hint=EXPLAIN
    -> ToolExecutor con sólo source.find_symbol,
       source.find_model_extensions y source.read_excerpt
    -> Evidence(source, checked) capturada desde el ledger cerrado
    -> validación host-side de AnswerEnvelope y refs
    -> citas record/source reducidas
    -> Odoo revalida el shape y la pertenencia al current record
    -> panel Owl renderiza texto y citas lógicas con t-esc
```

El contrato M2 `POST /v1/turns/context-read` permanece disponible. El browser
no habla con el Assistant Service y no recibe delegation token, shared secret,
URLs internas, identidad autoritativa, Evidence completa ni transcript de
dynamic tools.

## Reglas deterministas del AnswerEnvelope

- `workflow` debe ser `EXPLAIN` y `proposed_action` debe ser `null`.
- La respuesta y las limitaciones tienen caps server-side.
- Las refs duplicadas se normalizan conservando su primer orden.
- Cada ref debe resolver al ledger del mismo turn; un UUID inventado falla
  cerrado.
- Sólo Evidence `checked` puede convertirse en una cita M4.
- Sólo `record` y `source` tienen representación de presentación en este slice.
- La cita record debe coincidir con el `model/res_id` releído del ScreenContext.
- La cita source sólo contiene módulo, logical path normalizado, líneas,
  fingerprint y provenance; nunca un root o path físico.
- `high` exige que la respuesta cite record y source comprobados. Si falta uno,
  el host reduce la confianza a `medium` y añade una limitación explícita.
- Un source stale/unavailable nunca crea Evidence checked; el turn devuelve una
  limitación degradada o `evidence_unavailable`, según el punto del fallo.

## Response browser-facing exacto

```json
{
  "ok": true,
  "turn_id": "12345678-1234-5678-1234-567812345678",
  "answer": "Texto no confiable renderizado con t-esc.",
  "confidence": "high",
  "limitations": [],
  "citations": [
    {
      "kind": "record",
      "evidence_id": "11111111-1111-4111-8111-111111111111",
      "model": "sale.order",
      "id": 42,
      "display_name": "S00042",
      "captured_at": "2026-08-22T14:00:00Z"
    },
    {
      "kind": "source",
      "evidence_id": "22222222-2222-4222-8222-222222222222",
      "module": "odoo_ai_m3_sale_project",
      "logical_path": "odoo_ai_m3_sale_project/models/sale_order.py",
      "start_line": 9,
      "end_line": 28,
      "fingerprint": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "provenance": "third_party_or_custom"
    }
  ]
}
```

Los fallos browser-facing conservan sólo `{"ok": false, "error": {"code":
"..."}}`, con códigos acotados para access denied, contexto, autenticación,
engine, evidencia, timeout y response inválida.

## Evidencia de cierre

- Quality completa de M4: 308 passed, 8 skipped con DB real; Ruff y mypy
  estricto verdes.
- Addon Odoo 18 sobre PostgreSQL 16 desechable: install y update, cada uno con
  25 tests y 0 fallos/errores.
- Runner Chromium de Odoo 18 `WebSuite.test_unit_desktop` filtrado al addon: 1
  suite y 0 fallos/errores.
- `assistant_panel_service.test.js` comprueba que `<script>`, HTML arbitrario y
  `javascript:` permanecen como texto, y que dos submits simultáneos producen
  una sola llamada RPC.
- El template no usa `t-raw` ni `innerHTML`; respuesta, limitaciones, paths y
  fingerprints se renderizan con `t-esc`.

El E2E real y el gate integral están registrados en
[`M4_E2E_REPORT.md`](M4_E2E_REPORT.md) y
[`M4_GATE_REPORT.md`](../M4_GATE_REPORT.md).

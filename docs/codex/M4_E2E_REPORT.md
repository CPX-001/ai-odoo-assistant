# M4-09 — E2E real de `sale.order` con Codex

Fecha: 2026-08-22. Resultado: **PASS**.

## Caso demostrado

Pregunta desde el panel Odoo: `¿Por qué al confirmar este pedido se crea una
tarea?`

La respuesta generada por Codex explicó que la extensión
`odoo_ai_m3_sale_project` sobrescribe `sale.order.action_confirm`, comprueba la
referencia fixture y crea una `project.task`. No se fijó la prosa exacta.

Evidencia desechable observada:

- record: `sale.order #1`, `S00001`, releído por ORM con `captured_at`;
- source: `odoo_ai_m3_sale_project/models/sale_order.py`, líneas 1-28,
  fingerprint `sha256:c21218448a722ddfbd7c71f15590d7374966c3c73c68fafe706adf35d74eacaa`;
- efecto: pedido en estado `sale` y exactamente una tarea
  `M3 diagnostic task for S00001`;
- tools: `find_model_extensions` ×1, `find_symbol` ×2 y `read_excerpt` ×2.

## Boundaries y negativos

- Chromium hizo cero requests directos al Assistant Service y no observó
  delegation/shared secrets, credenciales, roots ni headers internos.
- El usuario sin acceso obtuvo `access_denied` antes de una explicación.
- Tras alterar sólo el source temporal, no se emitió una respuesta inventada de
  alta confianza; el fallo quedó acotado como `engine_unavailable`.
- Al retirar el ejecutable Codex, readiness pasó a `DEGRADED` y la UI mostró
  `engine_unavailable` sin detener Odoo.
- Los tests deterministas confirman que un presupuesto insuficiente corta el
  loop sin invocar el handler fuera de límite.
- El runner confirmó que el rol del Assistant no podía conectar a la DB Odoo y
  eliminó procesos, DBs, roles y fixtures temporales.

Runner: [`tests/e2e/run_m4_sale_order_codex.py`](../../tests/e2e/run_m4_sale_order_codex.py).

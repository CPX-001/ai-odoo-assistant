# M5-09 — E2E real QUERY + HOW_TO con Codex

Fecha: 2026-08-23. Resultado: **PASS**.

## Vertical slice demostrado

El runner desechable instaló Odoo 18 Community con el addon de producto y una
fixture propia, preparó una Assistant DB migrada, indexó un documento temporal,
levantó Assistant Service + Codex App Server y condujo Chromium exclusivamente
contra Odoo.

QUERY se ejecutó sobre `odoo.ai.m5.guided.item`:

- usuario A: aggregate exacto de registros `Open` visibles = **2**;
- usuario B: la misma pregunta y modelo = **1**;
- tools reales: `odoo.get_effective_schema` y `odoo.aggregate_records`;
- la record rule ocultó el registro del otro usuario y su canary no apareció en
  respuesta, citas, intercambio browser ni traces.

HOW_TO combinó hechos de la instalación fixture:

- ruta visible `M5 Guidance > Guided Items`;
- schema efectivo del modelo y campo `guide_code`;
- documento lógico `guided-items.md`, con fingerprint vigente;
- tools reales: `knowledge.search` (reintento lexical bounded) y
  `knowledge.read_excerpt`;
- citas browser-safe de tipos `navigation`, `schema` y `document`.

## Negativos y límites

- Una petición de borrado no ejecutó tools de write y terminó en
  `query_rejected`.
- Al retirar el documento y reingerir el provider, se retiró un documento; el
  fingerprint anterior no reapareció y HOW_TO devolvió una respuesta acotada
  sin cita documental stale de alta confianza.
- Sin ejecutable Codex, readiness pasó a `DEGRADED` y el panel recibió
  `engine_unavailable`; Odoo siguió operativo.
- Chromium realizó cero requests directos al Assistant Service y no observó
  shared/delegation secrets, credenciales ni roots físicos.
- El rol Assistant no pudo conectar a la DB Odoo. No hubo SQL directo del
  Assistant contra datos Odoo ni capacidad M6.

## Cleanup

El runner detuvo los procesos y eliminó sus DBs, roles, secrets, knowledge root,
addons fixture y directorio de trabajo aleatorios. El bootstrap PostgreSQL 16
usa membership explícita para asignar ownership, sin depender de privilegios
implícitos de versiones anteriores.

Runner: [`tests/e2e/run_m5_query_how_to_codex.py`](../../tests/e2e/run_m5_query_how_to_codex.py).

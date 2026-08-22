# M3 — Gate report

Fecha de ejecución: 2026-08-22. Veredicto: **PASS**.

## Alcance

La gate se ejecutó contra Odoo 18 Community y PostgreSQL 16 con bases, puertos,
roots de addons, fichero de log y units desechables. Se contrastó con el Source
of Truth, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT_CONFIG.md` y
`docs/codex/tasks/M3/M3-10-gate.md`.

M3-10 no añadió funcionalidad. La integración real con journald descubrió un
defecto de M3: el prefijo que journal añade a cada línea impedía reconocer la
excepción final del traceback. Se corrigió el stripping determinista del
prefijo y se añadió una regresión con el formato real antes de repetir la gate.

## Calidad y regresiones

| Check | Resultado | Evidencia/comando |
| --- | --- | --- |
| pytest completo | PASS | Con `ODOO_AI_TEST_DATABASE_URL=postgresql+psycopg://127.0.0.1:55479/odoo_ai_test`, desde `service/`: `../.venv/bin/python -m pytest` → **215 passed, 5 skipped**. Los cinco perfiles reales omitidos se ejecutaron por separado y pasaron. |
| Ruff | PASS | Desde `service/`: `../.venv/bin/ruff check src ../installer ../tests ../addons` → `All checks passed!`. |
| mypy | PASS | Desde `service/`: `../.venv/bin/mypy src` → `Success: no issues found in 48 source files`. |
| migraciones | PASS | `tests/integration/test_migrations.py` → 3 casos verdes: upgrade idempotente, upgrade desde la revisión M1 y fresh database desde `base` hasta `head`. |
| addon Odoo 18 | PASS | PostgreSQL UTF-8 desechable; `odoo-bin --init odoo_ai_assistant,odoo_ai_m3_sale_project` y después `--update` con `--test-enable --test-tags=/odoo_ai_assistant,/odoo_ai_m3_sale_project` → **0 failed, 0 errors of 23 tests** en ambos recorridos. |
| M1 PostgreSQL | PASS | `installer/smoke/m1_gate.sh postgres` → 1 passed. |
| M1 runtime | PASS | `installer/smoke/m1_gate.sh runtime` → 1 passed. |
| M1 systemd | PASS | Como root en el entorno desechable: `installer/smoke/m1_gate.sh systemd` → 1 passed. |
| M1 Odoo | PASS | Como root en el entorno desechable: `installer/smoke/m1_gate.sh odoo` → 1 passed. |
| layout alternativo | PASS | Como root en el entorno desechable: `installer/smoke/m1_gate.sh alternate` → 1 passed. |
| M2 browser E2E | PASS | Odoo y Assistant Service reales, Playwright/Chromium: `positive_display_name=S00001`, `positive_status=ok`, `negative_error=access_denied`, `browser_to_assistant_requests=0`; el único origen observado fue Odoo. |

Los paths concretos del runner Odoo usados por esta gate son evidencia del
entorno DEV, no defaults ni contratos de producto.

## Source

| Invariante | Resultado y cobertura |
| --- | --- |
| roots resueltos y configurables | PASS. `test_source_scanner.py` cubre precedencia, roots validados y rechazo de escapes; el E2E usa un root no convencional con espacios obtenido del inventario runtime. |
| sin scan host-wide | PASS. El scanner sólo recibe `ResolvedSourceRoot`; Diagnostics no acepta roots ni paths en el request. |
| manifest literal/dinámico | PASS. `test_source_extractors.py` valida evaluación literal y que un manifest dinámico no se ejecuta. |
| Python AST | PASS. Se encuentran clases, `_inherit` y métodos sin importar el addon. |
| XML y CSV security | PASS. `test_source_xml_csv.py` cubre parsing acotado, entidades externas rechazadas y declaraciones estáticas de seguridad. |
| símbolo y líneas exactas | PASS. El fixture `sale.order.action_confirm` se resuelve como `odoo_ai_m3_sale_project/models/sale_order.py`, líneas **9–28**. |
| extensiones y excerpt | PASS. `find_model_extensions` es estructural/conservador; `read_excerpt` exige una ref emitida, revalida root+fingerprint y aplica caps de líneas/bytes. |
| incremental, deletion y stale | PASS. La suite verifica archivos unchanged, cleanup de borrados y fingerprints; el E2E cambia el source, recibe `stale_source`, reescanea y obtiene fingerprints nuevos de scan y candidato. |
| provenance | PASS. Se mantiene conservadora y no clasifica `custom` sólo por el path. |

El E2E autenticado ejecutó, en orden, `source/rescan`, `source/test`, lectura del
excerpt, mutación del fixture, rechazo stale, nuevo scan y nueva lectura. Ningún
path físico apareció en las respuestas.

## Logs

| Invariante | Resultado y cobertura |
| --- | --- |
| File provider real | PASS. El E2E usa un fichero fixture en un path no convencional, filtra por ventana+término y devuelve el traceback esperado. |
| Journal provider | PASS. Tests de contract validan argv fijo, timeout y caps. Una unit systemd desechable se consultó con `journalctl` real → `journal_provider=PASS`, fingerprint `sha256:5b973760917d6968a72c30af87e2b810db3e7c5c8329bb76c04d35278d77f3a8`, 1 occurrence, 317 bytes. |
| ventana, terms y caps | PASS. Los providers aplican ventana, terms literales, máximo de líneas, bytes, fetch y tiempo server-side. |
| traceback, grouping y fingerprint | PASS. Parsing y reread por fingerprint emitido están verdes; fingerprints normalizan IDs, direcciones, paths y números de línea volátiles. |
| redacción | PASS. Los secretos de fixtures y formas `password`/`token` se sustituyen antes de salir del provider. |
| no full ingest | PASS. La consulta es bajo demanda y sólo persiste estado/fingerprints, no el log completo. |

## Seguridad y deployment

- Búsqueda estática en `service/src` y `addons/odoo_ai_assistant` para
  `sudo(`, `execute_kw`, `execute_method`, `shell=True`, `env.cr.execute` y
  `cursor.execute`: **0 matches** en runtime productivo.
- Búsqueda de `/etc/odoo`, `odoo.service`, `/var/log/odoo` y `/opt/odoo` en el
  runtime productivo: **0 matches**.
- Journal construye un argv fijo, usa `shell=False` y rechaza units maliciosas o
  ambiguas. Diagnostics no acepta unit, log path, source path ni command text.
- File provider revalida fichero regular, root permitido y escapes por symlink;
  los estados missing/no-permission/error están sanitizados.
- Los requests y responses de Diagnostics están acotados. El browser no conoce
  las rutas admin del Assistant Service, secretos, tokens, roots ni providers
  físicos; todas las llamadas salen del servidor Odoo.
- Override externo de source roots, log file y journal unit funciona sin editar
  Python. Inventario runtime y layout alternativo cubren autodetección y
  deployment no convencional.
- No se implementaron Codex, tools dinámicas, RAG, QUERY, writes, approvals ni
  business actions de M4+.

## Estado observable

El E2E de Diagnostics confirmó Assistant DB y migrations en `OK`, `source` en
`OK`, `logs` en `OK` y el contextual read de M2 operativo. El status mantiene
correctamente `readiness=DEGRADED` y `pending_capabilities=[reasoning_engine]`:
M4 aún no ha comenzado.

No se detectó ningún conflicto abierto con el Source of Truth ni fue necesario
crear un ADR.

**M3 GATE: PASS**

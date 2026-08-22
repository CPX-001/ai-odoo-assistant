# M2 — Gate report

Fecha de ejecución: 2026-08-22. Veredicto: **PASS**.

## Alcance

La gate se ejecutó contra Odoo 18 Community y PostgreSQL 16 en una topología
desechable con dos bases separadas: una para Odoo y otra para el Assistant
Service. La revisión se contrastó con el Source of Truth, la arquitectura, la
política de deployment y `docs/codex/tasks/M2/M2-09-gate.md`.

La validación no añadió features. Los únicos cambios de código de esta task son
ajustes mecánicos de lint y comentarios de excepciones deliberadamente amplias
en límites HTTP/Odoo que sanitizan el error antes de devolverlo.

## Resultado

| Check | Resultado | Evidencia/comando |
| --- | --- | --- |
| tests | PASS | `installer/smoke/m1_gate.sh quality`: 145 passed, 11 skipped; los perfiles omitidos se ejecutaron por separado. Addon Odoo: 28 tests y 0 fallos tanto en instalación como en actualización. |
| lint | PASS | Desde `service/`: `../.venv/bin/ruff check src ../installer ../tests ../addons`. |
| type-check | PASS | `installer/smoke/m1_gate.sh quality`: mypy estricto, 32 source files sin errores. |
| addon install/upgrade | PASS | Base Odoo UTF-8 recién creada; `--init=sale,odoo_ai_assistant` y después `--update=odoo_ai_assistant`, ambos con `--test-enable --test-tags=/odoo_ai_assistant`. Versión instalada: `18.0.2.8.0`. |
| panel + ScreenContext | PASS | Chromium abrió el form real de `S00001`, mostró el panel y capturó `sale.order #1`; el request contenía sólo `message` y `screen`, con model/res_id correctos y sin identidad. Los casos sin registro están cubiertos por los tests de captura y contratos. |
| server-side identity | PASS | Tests del bridge y de `turn_context`: uid, compañía y compañías permitidas se derivan de `env`; identidad aportada por browser se rechaza. |
| delegation tamper/expiry/scope | PASS | Tests de codec y addon cubren firma, versión, TTL, turn/DB/user/company/model/IDs/scopes y consumo único por `(jti, scope)`. Tampering, expiración, scope incorrecto y replay se rechazan. |
| ACL/record rules/fields | PASS | Tests Odoo reales validan ACL, record rules, filtrado de campos inaccesibles, límites de campos/bytes y rechazo uniforme sin filtrar existencia. |
| multi-company | PASS | Tests Odoo reales prueban que una compañía no autorizada y un registro de otra compañía no amplían autoridad. |
| OdooGateway real | PASS | El E2E usó el adapter HTTP real con URL server-side, timeouts, caps y redirects desactivados; su port conserva sólo metadata y lectura acotadas. |
| context-read API | PASS | `POST /v1/turns/context-read` autenticado revalidó schemas/limits, releyó por gateway y devolvió una respuesta determinista. 14 trazas inspeccionadas y 0 filas con pregunta cruda, token o secretos de prueba. |
| sale.order E2E | PASS | Harness Playwright: `positive_display_name=S00001`, `positive_status=ok`; cambiar el contexto a `S00002`, oculto por record rule al mismo usuario no-admin, devolvió `access_denied`. |
| browser boundary | PASS | Origen observado por Chromium: sólo Odoo (`http://127.0.0.1:18088`); 0 requests browser → Assistant Service y 0 secretos/tokens en los intercambios del bridge. |
| M1 regression | PASS | `m1_gate.sh quality`, `postgres`, `runtime`, `systemd`, `odoo` y `alternate`: todos verdes. `/health` devolvió `ok`; `/v1/admin/status` autenticado confirmó Assistant DB disponible y Alembic en `0002_m1_03_runtime_tables`. |

El status administrativo permanece correctamente en `DEGRADED`: `source`,
`logs` y `reasoning_engine` son capacidades pendientes de milestones
posteriores, no regresiones de M2.

## Revisión general

- `contracts` no importa Odoo, FastAPI ni storage; `application` depende de
  ports/contratos, no del adapter HTTP concreto.
- No hay `execute_kw`, `execute_method`, shell, SQL ni Python arbitrarios como
  tool del agente.
- No hay `sudo()` en los caminos normales ni SQL del Assistant Service contra
  la base productiva de Odoo.
- El browser sólo transporta navegación y texto; no es fuente de identidad y no
  conoce secretos, tokens ni endpoints internos.
- No se han adelantado source/log providers, ReasoningEngine/Codex, RAG,
  writes, approvals ni actions de M3+.
- La inspección visual del resultado confirmó que el panel es operable y que
  muestra el contexto y la relectura ORM del pedido actual.

No se detectaron conflictos arquitectónicos ni fue necesario crear un ADR.

**M2 GATE: PASS**

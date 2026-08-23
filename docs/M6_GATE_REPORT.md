# M6 gate report

Fecha: 2026-08-23.

## Resultado ejecutivo

**M6 GATE: FAIL**

Los packets M6-07..M6-10 están implementados y la evidencia determinista está
verde, pero M6 no puede cerrarse por dos motivos independientes:

1. El Source of Truth exige para M6 `create/update` genérico seguro y al menos
   una business action curada. El plan de packets M6 acotó el primer slice a un
   `record_patch` update de un solo registro y excluyó create/business actions.
   No existe ADR ni actualización explícita del Source of Truth que resuelva
   esa desviación. Por ser un requirement no implementado y no un recurso
   externo, el veredicto no puede ser `CONDITIONAL`.
2. El E2E obligatorio Odoo 18 + Assistant PostgreSQL + Codex real + Chromium no
   pudo ejecutarse en este host: no existe `M6_POSTGRES_ADMIN_DSN` para un
   cluster desechable y el ejecutable Codex detectado por la app no es invocable
   desde WSL. El runner falla antes de crear recursos y no toca la instancia DEV.

M6 permanece abierto. No se inicia M7.

## Matriz del gate

| Check | Resultado | Evidencia |
| --- | --- | --- |
| quality / lint / mypy | PASS | `ruff check src ../tests ../addons/odoo_ai_assistant`; mypy: 94 source files sin issues; pytest: 447 passed, 35 skipped opt-in |
| migrations / addon | NOT RUN | Los 6 tests de migrations y los tests Odoo/install/update reales requieren PostgreSQL/entorno desechable no configurado; el runner M6 contiene fresh install + update pero se detuvo antes de crear recursos |
| M1-M5 regressions | PASS determinista | Suite completa verde; los reportes M1-M5 versionados conservan `PASS`. No se repitieron sus gates externos en este host |
| contracts / canonicalization | PASS | `record_patch` v1, 1-4 fields tipados, extra-forbid/strict, serialización canónica y fingerprint ligados a actor/target/schema/policy; tests de coerción y tampering incluidos |
| effective write schema / policy | PASS determinista | Schema runtime bajo uid/companies, tipos escalares allowlisted, fields/modelos sensibles bloqueados, revision/fingerprint revalidados; QUERY no cambia de registry |
| preview / no side effects | PASS determinista | Preview relee before real, valida after tipado, produce precondition + Evidence checked y no escribe; target/field/schema/payload mismatch fallan cerrado |
| approval / state machine | PASS determinista | Proposal durable, approve/reject/expiry/concurrency/replay/cross-actor ligados a payload, DB, uid, companies y expiry; reject no ejecuta |
| ACTION authority / commit | PASS determinista | `a1` separado de v1/q1/p1, TTL/bindings/replay, `su=False`, revalidación ACL/rules/field/policy/precondition, commit one-shot sin método genérico |
| verification / audit | PASS determinista | Success sólo tras reread exacta; stale/failed/unknown/unverified explícitos; resultado ambiguo se verifica sin retry ciego; audit sanitizado y correlacionable |
| Codex ACTION tools | PASS determinista | Registry ACTION exacta: `odoo.get_effective_write_schema` + `odoo.preview_record_patch`; el ToolExecutor default sigue READ/METADATA; no existe tool de approval/commit |
| browser / UI / security | PASS determinista | ACTION seleccionable, diff/target/warnings/expiry escapados, decisión mínima `proposal_id` + `decision`, actor derivado en Odoo, doble click bloqueado, estados no optimistas, sin browser -> Assistant |
| real ACTION E2E | NOT RUN | Runner reproducible implementado con happy/reject/ACL+record rule/multi-company/tampering/stale/expiry/injection/XSS/replay/fallo post-commit; ejecución bloqueada por dependencias externas indicadas arriba |
| Source of Truth scope | FAIL | Falta resolver create + business action curada frente al scope reducido de los packets M6 |
| scope containment M6 packets | PASS | No create/delete, bulk write, shell/SQL/Python, `execute_method`/`execute_kw`, approval autónoma, commit tool, Settings M7 ni checks Odoo 19 en application |

## Comandos y resultados reproducibles

Desde `service/`:

```text
../.venv/bin/ruff check src ../tests ../addons/odoo_ai_assistant
# All checks passed

../.venv/bin/mypy
# Success: no issues found in 94 source files

../.venv/bin/pytest -q
# 447 passed, 35 skipped in 29.55s
```

Los 35 skips son explícitos: PostgreSQL real no configurado (incluidas seis
pruebas de migrations/persistencia), cinco smokes Codex opt-in y smokes de
bootstrap/runtime/Odoo que requieren un host desechable o privilegios
específicos. No son fallos ocultos ni se convirtieron en PASS.

Validaciones adicionales:

```text
node --check tests/e2e/m6_action_browser.mjs
python3 -m py_compile tests/e2e/run_m6_action_codex.py \
  tests/e2e/m6_action_fixture.py
# OK

python3 -c "import xml.etree.ElementTree as E; ..."
# 4 XML files parsed
```

Intento del runner con los runtimes detectados y sin credenciales inventadas:

```text
M6_ODOO_PYTHON=<detected> M6_ODOO_BIN=<detected> \
M6_ODOO_CORE_ADDONS=<detected> M6_CODEX_EXECUTABLE=<detected> \
M6_PLAYWRIGHT_ROOT=<bundled> M6_NODE=<detected> \
.venv/bin/python tests/e2e/run_m6_action_codex.py
# M6_E2E_ERROR=M6_POSTGRES_ADMIN_DSN must be a PostgreSQL URI
```

El runner exige overrides explícitos para Python/bin/addons de Odoo, Codex,
Playwright/Node y el DSN administrador del cluster desechable. No contiene rutas,
usuarios, bases, puertos ni credenciales del cliente como contratos de producto.

## Runner M6-09 implementado

`tests/e2e/run_m6_action_codex.py` crea roles y bases Odoo/Assistant separados,
verifica que el rol Assistant no puede conectar a Odoo, instala y actualiza el
addon más el fixture test-only, aplica Alembic, arranca servicios en puertos
libres y ejecuta Chromium. El cleanup elimina únicamente nombres aleatorios
creados por esa ejecución.

La suite Chromium comprueba:

- preview exacta y ausencia de write antes de aprobación;
- commit aprobado y receipt `verified` con un write observado;
- cancelación terminal sin write;
- usuario/compañía B y record rule sin acceso ni leak;
- browser extra payload y approval cruzada rechazados;
- stale, expiry y replay sin write ACTION adicional;
- instrucciones de shell/SQL/Python/`odoo.write` tratadas como texto;
- HTML/script visible como datos sin ejecución;
- proxy loopback que entrega el commit real y corta una única respuesta; el
  Assistant relee y verifica antes de responder, sin segundo write;
- tools Codex exactas de schema + preview y cero requests Chromium -> Assistant;
- correlaciones proposal/approval/attempt/evidence y audit sin canaries/secrets.

## Versiones observadas

- Odoo Server 18.0.
- Python Odoo/service 3.12.3.
- PostgreSQL client 16.15; servidor local responde, pero el usuario actual no
  dispone de un DSN administrador desechable autorizado.
- Node.js 18.19.1.
- El runtime Codex está presente dentro de la aplicación de escritorio, pero su
  CLI no es ejecutable desde WSL; versión/handshake real M6 no verificados.

## Desviación pendiente y salida del gate

Para volver a ejecutar M6-10 hacen falta ambas cosas:

1. una decisión arquitectónica explícita: implementar y paquetizar create + una
   business action allowlisted, o aprobar un ADR y actualizar el Source of Truth
   para que el milestone M6 quede definido por el `record_patch` actual;
2. proporcionar un PostgreSQL admin DSN de un cluster desechable, un Codex CLI
   Linux autenticado/invocable y Playwright con Chromium, y ejecutar el runner
   hasta obtener `M6_E2E_RESULT` verde.

Hasta entonces no se cambia el roadmap a M6 completado ni se presenta el flujo
como listo para piloto.

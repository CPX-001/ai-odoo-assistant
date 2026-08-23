# M6 gate report

Fecha: 2026-08-23.

## Resultado ejecutivo

**M6 GATE: FAIL**

Los packets M6-01..M6-10 están implementados y el gate técnico completo está
verde, incluido el E2E real Odoo 18 + Assistant PostgreSQL + Codex + Chromium.
El milestone no puede declararse cerrado por una única desviación formal:

- el Source of Truth exige para M6 `create/update` genérico seguro y al menos
  una business action curada;
- el plan de packets M6 define deliberadamente un primer slice de update
  `record_patch` de un solo registro y excluye create/business actions;
- no existe ADR aceptado ni actualización explícita del Source of Truth que
  autorice esa reducción.

No se rebaja el veredicto a `CONDITIONAL`, porque ya no falta infraestructura
externa: falta resolver un requirement de producto. M6 permanece abierto y no
se inicia M7.

## Matriz del gate

| Check | Resultado | Evidencia |
| --- | --- | --- |
| quality / lint / mypy | PASS | Ruff verde; mypy: 94 source files sin issues; suite con PostgreSQL: 473 passed, 10 skipped opt-in |
| migrations / addon | PASS | Tests de migrations/persistencia activos sobre PostgreSQL desechable; runner real hizo fresh install + update de addon y fixture |
| M1-M5 regressions | PASS | Suite combinada verde; los reportes M1-M5 versionados conservan PASS |
| contracts / canonicalization | PASS | `record_patch` v1 bounded, strict/extra-forbid, payload canónico y fingerprint ligados a actor/target/schema/policy |
| effective write schema / policy | PASS | Schema runtime bajo uid/companies, campos/tipos sensibles bloqueados y revisions revalidadas |
| preview / no side effects | PASS | Before/after reales, precondition + Evidence checked y cero write antes de aprobación |
| approval / state machine | PASS | Persistencia durable; approve/reject/expired/stale/replay/concurrencia/cross-actor ligados al payload |
| ACTION authority / commit | PASS | `a1` separado, TTL/bindings/replay, `su=False`, revalidación ACL/rules/field/policy/precondition y write estrecho |
| verification / audit | PASS | Success sólo tras reread exacta; fallo ambiguo verificado sin retry; 20 eventos de audit sanitizados |
| Codex ACTION tools | PASS | Registry exacta: schema + preview; sin tool de approval/commit |
| browser / UI / security | PASS | Diff escapado, decisión mínima, actor derivado en Odoo, doble click protegido y cero browser -> Assistant |
| real ACTION E2E | PASS | Odoo 18 + Codex 0.149.0 + Chromium: happy/reject/ACL/rule/tampering/stale/expiry/XSS/replay/fallo post-commit |
| Source of Truth scope | FAIL | No están implementados create seguro + una business action curada y no hay ADR/SOT que cambie ese requirement |
| scope containment M6 packets | PASS | Sin delete/bulk/shell/SQL/Python, método genérico, approval autónoma, commit tool ni trabajo M7/M8 |

## Comandos y resultados reproducibles

Calidad y suite desde `service/`:

```text
../.venv/bin/ruff check src ../tests ../addons/odoo_ai_assistant
# All checks passed

../.venv/bin/mypy
# Success: no issues found in 94 source files

ODOO_AI_TEST_DATABASE_URL=postgresql+psycopg://<role>@127.0.0.1:<port>/<disposable-db> \
  ../.venv/bin/pytest -q
# 473 passed, 10 skipped in 34.31s
```

Los 10 skips restantes son smokes opt-in de otros runtimes/bootstraps: cinco
smokes Codex independientes y cinco pruebas que requieren instalación runtime,
PostgreSQL bootstrap, systemd o root. Las pruebas de migrations y persistencia
sí se ejecutaron. El gate M6 real cubrió por separado Codex, Odoo y Chromium.

Runner real desde la raíz, con dependencias externas explícitas:

```text
PLAYWRIGHT_BROWSERS_PATH=<browser-cache> \
M6_ODOO_PYTHON=<odoo-python> M6_ODOO_BIN=<odoo-bin> \
M6_ODOO_CORE_ADDONS=<odoo-addons-root> \
M6_CODEX_EXECUTABLE=<linux-codex> M6_PLAYWRIGHT_ROOT=<node-root> \
M6_NODE=<node> M6_POSTGRES_ADMIN_DSN=<disposable-admin-dsn> \
ODOO_AI_CODEX_HOME=<authenticated-profile> \
.venv/bin/python tests/e2e/run_m6_action_codex.py
```

Resultado sanitizado observado:

```text
M6_E2E_RESULT={
  "ambiguous_response_drops": 1,
  "audit_events": 20,
  "browser_to_assistant_requests": 0,
  "codex_version": "codex-cli 0.149.0",
  "expiry_error": "approval_expired",
  "full_readiness": "FULLY_READY",
  "odoo_version": "Odoo Server 18.0",
  "proposal_states": ["expired", "rejected", "stale", "verified"],
  "writes_expected": {
    "ambiguous": 1,
    "happy": 1,
    "reject": 0,
    "stale_action": 0,
    "xss": 0
  }
}
```

También pasaron `node --check tests/e2e/m6_action_browser.mjs`, el smoke real
del protocolo Codex App Server y las verificaciones Python/XML del packet.

## Evidencia del runner M6-09

`tests/e2e/run_m6_action_codex.py` crea roles y bases Odoo/Assistant separados,
impide que el rol Assistant conecte a Odoo, instala/actualiza addon + fixture,
aplica Alembic, arranca servicios en puertos libres y elimina únicamente sus
recursos aleatorios.

La suite Chromium demostró:

- preview exacta sin write y commit aprobado con receipt `verified`;
- reject terminal sin write;
- usuario/compañía B y record rule sin aprobación, lectura ni leak;
- payload browser extra y approval cruzada rechazados;
- stale, expiry y replay sin write ACTION adicional;
- instrucciones shell/SQL/Python y HTML/script tratadas como datos;
- un proxy entrega el commit y corta exactamente una respuesta; el Assistant
  relee y verifica, sin segundo write;
- tools Codex exactas de schema + preview;
- cero requests Chromium -> Assistant y ninguna credencial en la evidencia.

Durante el gate se detectó y corrigió una regresión real: el entorno de commit
intentaba leer el atributo de idioma propio de la autoridad preview, aunque la
autoridad `a1` no lo contiene por diseño. La regresión ahora tiene test unitario
y el commit real queda demostrado por el E2E.

## Versiones observadas

- Odoo Server 18.0.
- Python Odoo/service 3.12.3.
- PostgreSQL 16 en cluster temporal loopback aislado.
- Node.js 18.19.1 y Playwright 1.51.1 con Chromium temporal.
- Codex CLI Linux 0.149.0 autenticado; App Server y turns ACTION reales verdes.

## Desviación pendiente

Para convertir el veredicto global en PASS hace falta una decisión de producto
explícita, no otro ajuste del runner:

1. implementar y paquetizar create seguro + una business action explícitamente
   allowlisted, con sus contratos, preview, authority, idempotencia, E2E y gate;
   o
2. aceptar un ADR y actualizar el Source of Truth para redefinir M6 al slice
   `record_patch` implementado.

Hasta entonces los diez packets están implementados, pero el milestone M6 no se
marca completado ni listo para piloto.

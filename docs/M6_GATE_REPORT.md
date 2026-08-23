# M6 gate report

Fecha: 2026-08-23.

## Resultado ejecutivo

**M6 GATE: PASS**

M6-01..M6-13 están implementados y verificados. El alcance ya coincide con el
Source of Truth: existe update seguro (`record_patch`), create seguro
(`record_create`) y una acción de negocio real curada
(`sale.order.confirm.v1`). Las tres familias usan el mismo boundary obligatorio
`proposal → preview → approval → commit → verification`, bajo el usuario Odoo
real y sin conceder authority de commit a Codex o al browser.

## Matriz del gate

| Check | Resultado | Evidencia |
| --- | --- | --- |
| quality / lint / mypy | PASS | Ruff verde; mypy estricto: 94 source files; suite PostgreSQL: 507 passed, 10 skipped opt-in |
| migrations / addon | PASS | Alembic fresh `head` y upgrade `0008 → head`; runner real hizo fresh install + update del addon y fixture |
| M1-M5 regressions | PASS | Suite combinada verde; reportes M1-M5 conservan PASS |
| Source of Truth scope | PASS | Patch + create + business action curada implementados y demostrados E2E; no queda contradicción de alcance |
| contracts / canonicalization | PASS | Unión strict/extra-forbid y bounded; fingerprints ligados a actor, DB, compañías, target, policy, schema/spec y payload exacto |
| effective schemas / policy | PASS | Elegibilidad read/write/create bajo uid real; fields/models/tipos sensibles bloqueados; revisiones revalidadas |
| preview / no effects | PASS | Patch muestra before/after; create requested values/default warning; business action target/state/outcome; cero mutación antes de approval |
| approval / state machine | PASS | Approval durable; reject, expiry, stale, replay, tampering, concurrencia y cross-user/company fallan cerrados |
| commit authorities | PASS | Scopes separados por patch/create/business/verify, TTL y binding; `su=False`; sin raw create/write, method, context, kwargs o domain libres |
| create idempotency | PASS | Respuesta post-create perdida una vez; recovery devuelve el ID original; exactamente un registro creado |
| business idempotency | PASS | Receipt y confirmación en una transacción; pérdida de respuesta/replay no repite `action_confirm`; contador final 1 |
| verification / audit | PASS | Success sólo tras reread/outcome; Evidence checked; 48 eventos correlacionan proposal/approval/attempt/receipt sin secrets |
| Codex / tool boundaries | PASS | Tools sólo de schema/preview y estrechadas por intención; sin approval/commit/execute; registries EXPLAIN/QUERY/HOW_TO intactas |
| browser / UI / security | PASS | Preview escapada, decisión mínima, actor derivado en Odoo, doble click protegido y cero requests browser → Assistant |
| real E2E | PASS | Odoo 18 + Assistant PostgreSQL + Codex real + Chromium: happy/reject/ACL/stale/expiry/XSS/tampering/replay/response loss |
| scope containment | PASS | Sin delete/bulk/x2many arbitrario/shell/SQL/Python/método genérico/autonomous approval ni trabajo M7/M8 |

## Comandos y resultados reproducibles

Desde `service/`:

```text
../.venv/bin/ruff check src ../installer ../tests ../addons/odoo_ai_assistant
# All checks passed!

../.venv/bin/mypy src
# Success: no issues found in 94 source files

ODOO_AI_TEST_DATABASE_URL=postgresql+psycopg://<role>@127.0.0.1:<port>/<db> \
  ../.venv/bin/pytest -q
# 507 passed, 10 skipped in 44.76s
```

Los 10 skips son smokes opt-in: cinco de Codex y cinco de bootstrap/runtime que
requieren flags, root o systemd. El runner M6 ejecutó el Codex autenticado y el
stack ACTION real; los gates versionados M1-M5 conservan la evidencia de sus
smokes específicos. Tests de persistencia y migrations sí estuvieron activos
contra PostgreSQL.

Migraciones explícitas desde la raíz:

```text
ODOO_AI_DATABASE_NAME=<fresh-db> ODOO_AI_DATABASE_URL=<fresh-dsn> \
  .venv/bin/alembic upgrade head
ODOO_AI_DATABASE_NAME=<upgrade-db> ODOO_AI_DATABASE_URL=<upgrade-dsn> \
  .venv/bin/alembic upgrade 0008
ODOO_AI_DATABASE_NAME=<upgrade-db> ODOO_AI_DATABASE_URL=<upgrade-dsn> \
  .venv/bin/alembic upgrade head
# M6_MIGRATIONS_FRESH_AND_UPGRADE_PASS
```

Runner real desde la raíz, con dependencias externas explícitas y sin asumir
paths de deployment de cliente:

```text
PLAYWRIGHT_BROWSERS_PATH=<browser-cache> \
M6_ODOO_PYTHON=<odoo-python> M6_ODOO_BIN=<odoo-bin> \
M6_ODOO_CORE_ADDONS=<core-addons> M6_ODOO_EXTRA_ADDONS=<extra-addons> \
M6_CODEX_EXECUTABLE=<linux-codex> M6_PLAYWRIGHT_ROOT=<node-root> \
M6_NODE=<node> M6_POSTGRES_ADMIN_DSN=<disposable-admin-dsn> \
ODOO_AI_CODEX_HOME=<authenticated-profile> \
.venv/bin/python tests/e2e/run_m6_action_codex.py
```

Resultado sanitizado observado:

```text
M6_E2E_RESULT={
  "ambiguous_response_drops": {
    "business_action": 1,
    "record_create": 1,
    "record_patch": 1
  },
  "audit_events": 48,
  "browser_to_assistant_requests": 0,
  "completion": {
    "business_ambiguous": "verified",
    "business_happy": "verified",
    "create_ambiguous": "verified",
    "create_happy": "verified"
  },
  "expiry_error": "approval_expired",
  "full_readiness": "FULLY_READY",
  "proposal_states": ["expired", "rejected", "stale", "verified"],
  "tool_names": {
    "business_happy": ["odoo.preview_business_action"],
    "create_happy": [
      "odoo.get_effective_write_schema",
      "odoo.preview_record_create"
    ],
    "happy": [
      "odoo.get_effective_write_schema",
      "odoo.preview_record_patch"
    ]
  },
  "writes_expected": {
    "ambiguous": 1,
    "happy": 1,
    "reject": 0,
    "stale_action": 0,
    "xss": 0
  }
}
```

## Evidencia funcional y de seguridad

El runner crea roles y bases Odoo/Assistant separados, impide al rol Assistant
conectar a Odoo, aplica Alembic, instala y actualiza addon + fixture, arranca
servicios en loopback y usa Chromium contra Odoo. Un proxy entrega cada commit
y corta exactamente una respuesta por familia; el receipt permite reconciliar
sin repetir el efecto.

La suite real demostró:

- patch aprobado y verificado; reject, stale, expiry y XSS con cero write;
- create natural aprobado, exactamente un registro, reject con cero create y
  recuperación del ID original tras respuesta perdida;
- confirmación real de una cotización válida mediante el handler dedicado,
  outcome `sale`, reject/stale/ACL sin acción y contador exactamente 1 ante
  response loss/replay;
- separación multiempresa y record rules sin leaks;
- payload extras, proposal cruzada, fingerprint/action no allowlisted y replay
  rechazados;
- instrucciones de shell, SQL, Python y método arbitrario tratadas como datos;
- cero tráfico Chromium → Assistant y ausencia de secrets/authority/DSN en
  DOM, respuestas, Evidence y audit.

## Versiones observadas

- Odoo Server 18.0.
- Python 3.12.3.
- PostgreSQL 16.15 en cluster temporal loopback.
- Node.js 18.19.1, Playwright 1.55.0 y Chromium 140.0.7339.16.
- Codex CLI Linux 0.149.0-alpha.4.1 autenticado.

## Cierre

No queda blocker M6 ni se necesitó ADR para reducir alcance. M0-M6 quedan
cerrados con gate PASS. M7 es el siguiente milestone y no se inicia en este
cambio.

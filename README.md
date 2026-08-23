# Odoo AI Assistant

Odoo AI Assistant será un agente integrado en Odoo que combinará contexto de la instalación, evidencia verificable y operaciones acotadas bajo los permisos reales del usuario.

**M0-M6 están completados y sus gates son PASS; M7-01..04 están implementados y verificados en runtime, mientras M7-05..09 siguen pendientes.** El repositorio contiene el package Python del Assistant Service, sus contratos y ports base, el runtime HTTP, el addon Odoo, el bootstrap instalable de host, delegación/lecturas ORM bajo el usuario real, source/log evidence, Codex App Server como `ReasoningEngine`, `ToolExecutor`, el vertical slice real `EXPLAIN` con citas, schemas efectivos runtime, metadata de navegación visible, QUERY acotado, HOW_TO con knowledge incremental/retrieval mediante PostgreSQL FTS y ACTION segura para update, create y `sale.order.confirm.v1` mediante preview, aprobación, commit y verificación.

Baseline: Odoo 18 Community, Linux self-hosted y PostgreSQL, en un monorepo propio con esta separación general:

```text
Odoo addon
    ↓
Assistant Service
    ↓
Evidence / Tools / Reasoning
```

La especificación principal está en [`docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`](docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf). La referencia operativa resumida está en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) y la política de deployments configurables en [`docs/DEPLOYMENT_CONFIG.md`](docs/DEPLOYMENT_CONFIG.md).

El roadmap va de M0 (repo y contratos) a M8 (compatibilidad Odoo 19) y se resume en [`docs/codex/MILESTONES.md`](docs/codex/MILESTONES.md). El cierre de M6 está en [`docs/codex/tasks/M6/README.md`](docs/codex/tasks/M6/README.md) y su evidencia en [`docs/M6_GATE_REPORT.md`](docs/M6_GATE_REPORT.md). El plan ejecutable de M7 está en [`docs/codex/tasks/M7/README.md`](docs/codex/tasks/M7/README.md), incluyendo la agrupación 3+3+3 recomendada para Goal Mode.

## Arranque DEV del Assistant Service

Desde la raíz del repositorio, instala el package en un entorno virtual y arráncalo en loopback:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e './service[dev]'
.venv/bin/odoo-ai-service
```

El proceso escucha por defecto en `127.0.0.1:8000`. La comprobación de liveness es:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

Este endpoint no comprueba DB, migraciones ni readiness; el estado administrativo se consulta mediante `/v1/admin/status`.

## Gateway interno hacia Odoo

El adapter HTTP de M2 resuelve la URL base de Odoo exclusivamente desde
`ODOO_AI_ODOO_BASE_URL`. No existe un host o puerto de cliente hardcodeado; por
ejemplo, un deployment puede configurar `http://odoo.internal:18069`. La URL
debe ser `http` o `https`, sin credentials, path, query ni fragmento. El
shared secret continúa leyéndose desde `ODOO_AI_SHARED_SECRET_FILE`; el token
de delegación y el `turn_id` se ligan a una instancia del gateway por turn y no
forman parte del port público.

Los commits ACTION usan además una autoridad `a1` de un solo uso y key purpose
separado. Tanto el Assistant Service como el proceso Odoo deben recibir la ruta
del mismo secret file mediante `ODOO_AI_ACTION_AUTHORITY_SECRET_FILE`. El file
debe ser regular, tener al menos 43 bytes y no conceder permisos a `other`; no
se incluye nunca en requests, logs, receipts ni audit.

## Turno contextual determinista de M2

El Odoo server envía el contexto actual a `POST /v1/turns/context-read`; deriva
la identidad efectiva y la delegación sin confiar esos datos al navegador. El
servicio descubre metadata y relee por ORM sólo los campos disponibles entre
`display_name`, `name`, `state` y `company_id`.

Ejemplo de request server-to-server, con la delegación deliberadamente
redactada:

```json
{
  "turn_id": "018f6f1d-9d66-7b8c-a274-29f820cfad53",
  "message": "What is the state of this record?",
  "screen": {
    "view_type": "form",
    "model": "sale.order",
    "res_id": 42,
    "selected_ids": [42],
    "allowed_context_subset": {
      "active_model": "sale.order",
      "active_id": 42,
      "active_ids": [42]
    },
    "captured_at": "2026-08-21T10:30:00Z"
  },
  "user": {
    "uid": 17,
    "company_id": 1,
    "allowed_company_ids": [1],
    "lang": "en_US"
  },
  "delegation_token": "<server-only redacted>",
  "gateway": {"database": "acme"}
}
```

La respuesta que Odoo reduce para el browser no incluye evidencia interna,
identidad, instancia ni tokens:

```json
{
  "ok": true,
  "turn_id": "018f6f1d-9d66-7b8c-a274-29f820cfad53",
  "message": "El registro actual se ha releído mediante ORM.",
  "context": {
    "model": "sale.order",
    "res_id": 42,
    "display_name": "S00042",
    "captured_at": "2026-08-21T10:30:00Z"
  },
  "fields": {"name": "S00042", "state": "sale"}
}
```

## Migraciones de la Assistant DB

La conexión se configura externamente mediante `ODOO_AI_DATABASE_URL`. El nombre esperado se controla mediante `ODOO_AI_DATABASE_NAME` (default `odoo_ai`); una URL dirigida a otra DB se rechaza antes de crear el engine.

Con ambas variables disponibles, aplica las migraciones desde la raíz del repositorio:

```bash
.venv/bin/alembic -c alembic.ini upgrade head
```

La configuración y los logs no deben contener credenciales reales. La creación y el aislamiento del role y de la Assistant DB están implementados por el bootstrap de M1.

## Estado administrativo

`GET /v1/admin/status` comprueba el runtime y las capabilities del Assistant mediante el shared secret server-side. Con DB/migraciones, source, logs y reasoning realmente operativos, el estado puede llegar a `FULLY_READY`; si Codex no está disponible, el servicio degrada a `DEGRADED` sin detener Odoo y expone únicamente un error sanitizado. M5 añade capabilities diagnósticas separadas para schema/query, navegación y knowledge/HOW_TO sin alterar esa fórmula histórica de readiness. M6 añade ACTION transaccional con approval persistida, authorities one-shot, commit acotado y verificación para patch/create y una acción de negocio curada. M7-01..04 añaden configuración administrable acotada y Diagnostics estructurado; M7-05..09 siguen pendientes.

La base ACTION implementada y sus límites están documentados en [`docs/M6_ACTION_FOUNDATION.md`](docs/M6_ACTION_FOUNDATION.md).

## Bootstrap del host

Las rutas convencionales son sólo hints. Primero puede ejecutarse un preflight seguro:

```bash
python3 -m installer.bootstrap --preflight-only
```

Si la instalación usa nombres/rutas no convencionales, se pasan como overrides sin tocar código:

```bash
python3 -m installer.bootstrap --preflight-only \
  --odoo-conf /srv/acme/config/production.conf \
  --odoo-service acme-erp.service \
  --odoo-user acme-odoo \
  --addons-path /srv/acme/addons \
  --addons-path /mnt/oca \
  --odoo-data-dir /srv/acme/data \
  --odoo-log-file '/srv/acme/logs/odoo production.log'
```

`odoo.conf` y systemd no son requisitos absolutos para detectar Odoo: si no hay config conocida, los valores pueden quedar sin resolver y aportarse mediante overrides; si Odoo no usa systemd, `--odoo-user` permite continuar sin inventar un unit.

La preparación real requiere una única ejecución privilegiada. Crea/reutiliza el usuario y grupo del Assistant, directorios runtime, config no secreta y un shared secret con permisos restrictivos:

```bash
sudo python3 -m installer.bootstrap \
  --odoo-user acme-odoo \
  --install-dir /opt/odoo-ai-assistant \
  --config-dir /etc/odoo-ai-assistant \
  --state-dir /var/lib/odoo-ai-assistant \
  --runtime-dir /run/odoo-ai-assistant \
  --assistant-port 8000 \
  --assistant-db-name odoo_ai
```

El bind del Assistant Service permanece limitado a loopback en el MVP por seguridad. El bootstrap instala un release versionado, prepara el role/DB aislados, aplica Alembic e instala/verifica la unit systemd. Repetirlo valida recursos y corrige únicamente drift seguro.

El procedimiento de instalación, upgrade, backup, rollback y los smokes reproducibles están en [`docs/OPERATIONS_M1.md`](docs/OPERATIONS_M1.md).
La evidencia y el veredicto de M1 están en [`docs/M1_GATE_REPORT.md`](docs/M1_GATE_REPORT.md).
La evidencia y el veredicto de M2 están en [`docs/M2_GATE_REPORT.md`](docs/M2_GATE_REPORT.md).
La evidencia y el veredicto de M3 están en [`docs/M3_GATE_REPORT.md`](docs/M3_GATE_REPORT.md).
La evidencia y el veredicto de M4 están en [`docs/M4_GATE_REPORT.md`](docs/M4_GATE_REPORT.md); el E2E real está en [`docs/codex/M4_E2E_REPORT.md`](docs/codex/M4_E2E_REPORT.md).
La evidencia y el veredicto de M5 están en [`docs/M5_GATE_REPORT.md`](docs/M5_GATE_REPORT.md).
La evidencia y el veredicto de M6 están en [`docs/M6_GATE_REPORT.md`](docs/M6_GATE_REPORT.md).

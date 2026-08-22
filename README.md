# Odoo AI Assistant

Odoo AI Assistant será un agente integrado en Odoo que combinará contexto de la instalación, evidencia verificable y operaciones acotadas bajo los permisos reales del usuario.

M0, M1 y M2 están completados; sus gates son PASS. El repositorio contiene el package Python del Assistant Service, sus contratos y ports base, el runtime HTTP, el addon de diagnóstico, el bootstrap instalable de host y el vertical slice contextual de lectura bajo el usuario real. M3 — Source + logs está activo: M3-01 y M3-02 están implementados; M3-03 es el siguiente task packet.

Baseline: Odoo 18 Community, Linux self-hosted y PostgreSQL, en un monorepo propio con esta separación general:

```text
Odoo addon
    ↓
Assistant Service
    ↓
Evidence / Tools / Reasoning
```

La especificación principal está en [`docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`](docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf). La referencia operativa resumida está en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) y la política de deployments configurables en [`docs/DEPLOYMENT_CONFIG.md`](docs/DEPLOYMENT_CONFIG.md).

El roadmap va de M0 (repo y contratos) a M8 (compatibilidad Odoo 19) y se resume en [`docs/codex/MILESTONES.md`](docs/codex/MILESTONES.md).

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

`GET /v1/admin/status` comprueba el proceso, la conexión a la Assistant DB y la revisión de Alembic. Requiere el shared secret server-side y también resume el perfil/snapshot más reciente cuando existe. En M1 el resultado correcto sigue siendo `DEGRADED`, porque source, logs y reasoning engine todavía no están implementados.

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
La evidencia y el veredicto del milestone están en [`docs/M1_GATE_REPORT.md`](docs/M1_GATE_REPORT.md).
La evidencia del flujo contextual y el veredicto de M2 están en [`docs/M2_GATE_REPORT.md`](docs/M2_GATE_REPORT.md).

# Odoo AI Assistant

Odoo AI Assistant será un agente integrado en Odoo que combinará contexto de la instalación, evidencia verificable y operaciones acotadas bajo los permisos reales del usuario.

M0 está completado y M1 está en curso. El repositorio contiene el package Python del Assistant Service, sus contratos y ports base, y un runtime HTTP mínimo.

Baseline: Odoo 18 Community, Linux self-hosted y PostgreSQL, en un monorepo propio con esta separación general:

```text
Odoo addon
    ↓
Assistant Service
    ↓
Evidence / Tools / Reasoning
```

La especificación principal está en [`docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`](docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf). La referencia operativa resumida está en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

El roadmap va de M0 (repo y contratos) a M8 (compatibilidad Odoo 19) y se resume en [`docs/codex/MILESTONES.md`](docs/codex/MILESTONES.md).

## Arranque DEV del Assistant Service

Desde la raíz del repositorio, instala el package en un entorno virtual y arráncalo en loopback:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e './service[dev]'
.venv/bin/odoo-ai-service
```

El proceso escucha en `127.0.0.1:8000`. La comprobación de liveness es:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}
```

Este endpoint no comprueba DB, migraciones ni readiness; esas capacidades se incorporan en tasks posteriores de M1.

## Migraciones de la Assistant DB

La conexión se configura externamente mediante `ODOO_AI_DATABASE_URL`. El nombre de DB debe coincidir con `ODOO_AI_DATABASE_NAME`, cuyo valor por defecto es `odoo_ai`; una URL dirigida a otra DB se rechaza antes de crear el engine.

Con ambas variables disponibles, aplica las migraciones desde la raíz del repositorio:

```bash
.venv/bin/alembic -c alembic.ini upgrade head
```

La configuración y los logs no deben contener credenciales reales. La creación aislada del role y de la DB de producción pertenece a M1-06.

## Estado administrativo

`GET /v1/admin/status` comprueba el proceso, la conexión a la Assistant DB y la revisión de Alembic. También resume el perfil/snapshot más reciente cuando existe. En M1 el resultado correcto sigue siendo `DEGRADED`, porque source, logs y reasoning engine todavía no están implementados.

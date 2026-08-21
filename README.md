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

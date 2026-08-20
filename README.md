# Odoo AI Assistant

Odoo AI Assistant será un agente integrado en Odoo que combinará contexto de la instalación, evidencia verificable y operaciones acotadas bajo los permisos reales del usuario.

El proyecto está en su fase inicial, previa a M0. Este repositorio contiene únicamente instrucciones y documentación para preparar el desarrollo; todavía no incluye componentes funcionales.

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


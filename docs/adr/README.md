# Architecture Decision Records

Crear un ADR únicamente cuando se cambie o concrete una decisión arquitectónica significativa. Los ADR documentan el contexto, la decisión, consecuencias, alternativas y referencias; no sustituyen la actualización explícita del Source of Truth cuando cambie una invariante.

Los ADR-001 a ADR-013 ya están definidos en el Source of Truth y no se recrean como archivos independientes en esta fase. Para nuevas decisiones, copiar [`ADR-000-template.md`](ADR-000-template.md), asignar el siguiente identificador y mantener su estado actualizado.

ADR activos en el repositorio:

- [`ADR-014`](ADR-014-unified-host-authorized-agent.md): agente unificado con autoridad host-side.
- [`ADR-015`](ADR-015-batch-mutations-and-file-ingestion.md): mutaciones masivas, chunking e ingesta futura de archivos.
- [`ADR-016`](ADR-016-embedded-odoo-runtime.md): runtime operacionalmente autocontenido en el addon Odoo.
- [`ADR-017`](ADR-017-addon-capability-framework.md): framework interno de capabilities auto-descubiertas.
- [`ADR-018`](ADR-018-database-scoped-codex-activation.md): activación explícita de Codex por base Odoo sin duplicar el credential store.

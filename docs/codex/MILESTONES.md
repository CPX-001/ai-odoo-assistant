# Milestones

Este roadmap resume el Source of Truth. No autoriza por sí mismo la implementación de ningún milestone.

Estado actual: M0, M1 y M2 completados; gates de M1 y M2 PASS. M3 — Source + logs está activo; M3-01 a M3-09 están implementados y M3-10 es el siguiente task packet.

| Milestone | Objetivo observable |
| --- | --- |
| M0 — Repo / contratos | Monorepo y contratos mínimos con tests unitarios verdes y arquitectura congelada. |
| M1 — Runtime / install | Service instalable, con runtime y DB propios, detectado como healthy desde Odoo. El instalador no puede depender de rutas/nombres concretos del entorno DEV. |
| M2 — UI / context / delegation | Preguntar desde un pedido y releerlo como el usuario real mediante contexto y delegación firmada. |
| M3 — Source + logs | Encontrar `action_confirm` y un traceback desde Diagnostics con evidencia acotada, usando roots/providers resueltos en vez de paths hardcodeados. |
| M4 — Codex vertical slice | Resolver E2E por qué confirmar un pedido crea una tarea, citando registro y source exactos. |
| M5 — QUERY + HOW_TO + RAG | Ejecutar consultas server-side y ofrecer guías adaptadas a menús, schemas y knowledge de la instalación. |
| M6 — ACTION segura | Realizar desde chat un cambio simple aprobado, ligado al payload, releído y auditado. |
| M7 — Product hardening | Permitir que un técnico instale, actualice y opere el piloto sin consola diaria, con Diagnostics, Settings/overrides administrables y tests de seguridad. |
| M8 — Odoo 19 | Superar la misma contract suite y workflows en Odoo 19 sin cambios en `application`. |

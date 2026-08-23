# Milestones

Este roadmap resume el Source of Truth. No autoriza por sí mismo la implementación de ningún milestone.

Estado actual: **M0-M5 completados; gates PASS. M6-01..10 implementados y gate técnico real verde, pero M6 permanece abierto con gate FAIL por la desviación de alcance frente al Source of Truth. M6-11..13 están preparados para cerrar safe create + curated business action + gate final.**

| Milestone | Objetivo observable |
| --- | --- |
| M0 — Repo / contratos | Monorepo y contratos mínimos con tests unitarios verdes y arquitectura congelada. |
| M1 — Runtime / install | Service instalable, con runtime y DB propios, detectado como healthy desde Odoo. El instalador no puede depender de rutas/nombres concretos del entorno DEV. |
| M2 — UI / context / delegation | Preguntar desde un pedido y releerlo como el usuario real mediante contexto y delegación firmada. |
| M3 — Source + logs | Encontrar `action_confirm` y un traceback desde Diagnostics con evidencia acotada, usando roots/providers resueltos en vez de paths hardcodeados. |
| M4 — Codex vertical slice | Resolver E2E por qué confirmar un pedido crea una tarea, citando registro y source exactos. |
| M5 — QUERY + HOW_TO + RAG | Ejecutar consultas server-side y ofrecer guías adaptadas a menús, schemas y knowledge de la instalación. |
| M6 — ACTION segura | Realizar desde chat cambios create/update seguros y al menos una business action curada, siempre aprobados, ligados al payload, releídos y auditados. |
| M7 — Product hardening | Permitir que un técnico instale, actualice y opere el piloto sin consola diaria, con Diagnostics, Settings/overrides administrables y tests de seguridad. |
| M8 — Odoo 19 | Superar la misma contract suite y workflows en Odoo 19 sin cambios en `application`. |

El plan ejecutable y el Goal de cierre de M6 están en [`tasks/M6/README.md`](tasks/M6/README.md). M7 no se inicia hasta que M6-13 produzca `M6 GATE: PASS`.

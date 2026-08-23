# M7-05 — Maintenance operations Odoo-native

## Contexto

- Requiere M7-04 verde.
- Diagnostics ya puede identificar causas; ahora el administrador necesita ejecutar mantenimiento permitido sin shell diaria.
- El repo ya dispone de source rescan/test y log test; M7 debe unificar y completar la superficie operativa sin abrir un executor genérico.

## Objetivo

Exponer desde Odoo un conjunto pequeño de operaciones administrativas explícitas, bounded y auditadas para probar/reconstruir capabilities del Assistant sin conceder shell, filesystem libre ni control de procesos.

## Debes implementar

### Catálogo allowlisted de maintenance

Crear handlers/acciones explícitas para las operaciones realmente necesarias, como mínimo:

- refresh/test de overall readiness;
- source rescan y source test existentes;
- logs provider test existente;
- knowledge reindex/rescan según implementación M5;
- reasoning/Codex handshake/test;
- ACTION readiness/self-test sin ejecutar una acción de negocio real sobre datos productivos;
- config revalidation/reload sólo donde M7-03 lo permita.

Cada operación debe tener una key estable, input cerrado, timeout/caps, resultado sanitizado y audit event.

### Jobs/estado

Si una operación puede superar un request corto (source/knowledge), usar el patrón de job existente o introducir uno mínimo con:

- queued/running/succeeded/failed;
- timestamps;
- owner/admin actor;
- bounded progress/metrics;
- cancel sólo si la operación es realmente cancelable y seguro hacerlo;
- sin arbitrary command payload.

No construir un framework universal de jobs si no es necesario.

### UI

Diagnostics/Settings debe ofrecer sólo botones correspondientes a operations allowlisted y mostrar último resultado/estado. Evitar duplicar acciones equivalentes en varias pantallas sin necesidad.

## Debes reutilizar

- source rescan/test y log test actuales;
- knowledge ingestion/retrieval M5;
- reasoning readiness/handshake M4-M6;
- machine auth/admin checks;
- audit/status patterns existentes.

## Fuera de scope

- restart de servicios arbitrarios;
- shell/SQL/Python;
- editar archivos;
- ejecutar business actions como “test”;
- purge destructivo de DB;
- M8.

## Restricciones

- admin-only y server-derived actor;
- ninguna operation name libre desde browser/LLM;
- budgets/timeouts/replay donde aplique;
- results bounded/sanitized;
- una operación de test nunca debe escribir datos de negocio Odoo;
- failures no deben dejar config/index en estado intermedio silencioso.

## Tests obligatorios

- cada maintenance key válida ejecuta sólo su handler;
- unknown/tampered operation rechazada;
- non-admin denied;
- source/knowledge rebuild idempotente/recoverable;
- reasoning test no filtra auth/config;
- ACTION self-test no escribe registros de negocio;
- concurrent duplicate job controlado;
- timeout/failure deja estado interpretable y retry seguro;
- canary/secret absent en result/audit;
- UI no permite generic action dispatch;
- suite, Ruff y mypy.

## Acceptance criteria

- un técnico puede mantener source/log/knowledge/reasoning/readiness desde Odoo;
- no necesita shell para operaciones cotidianas del piloto;
- no existe una maintenance API genérica capaz de ejecutar comandos o métodos arbitrarios;
- cada operación deja estado y auditoría comprensibles.

## Después

1. Documenta catálogo final de operations y sus side-effect semantics.
2. Lista operaciones que siguen siendo setup-only.
3. No avances a M7-06 si alguna operation acepta nombres/payloads ejecutables libres.

## Estado de implementación

**Implemented / pending runtime verification.**

El catálogo final tiene ocho endpoints POST explícitos: readiness, source rescan,
source test, logs test, knowledge reindex, reasoning test, ACTION self-test y
configuration revalidation. No existe un endpoint que reciba una operation name
o un payload ejecutable desde browser/LLM.

`source_rescan` y `knowledge_reindex` usan únicamente un job persistido mínimo
(`queued/running/succeeded/failed`) con control de duplicados y recuperación de
jobs abandonados. El resto son probes directos y bounded. Cada intento deja
estado/audit en Assistant PostgreSQL; M7-06 ampliará la observabilidad y
retención, no la autoridad de ejecución.

Knowledge reindex reutiliza M5 y es transaccional: un scan incompleto revierte la
ingestión en vez de dejar un índice parcialmente aplicado. ACTION self-test sólo
comprueba authority + storage del Assistant y no crea ni ejecuta business
actions Odoo. Configuration revalidation no aplica cambios ni hace restart.

La UI Odoo deriva el actor desde `env.uid`/DB, retargetea los botones source/log
existentes para evitar duplicados y renderiza resultados desde una allowlist
local. El detalle del diseño y las operaciones que siguen siendo setup-only están
en `docs/M7_MAINTENANCE.md`.

Tests unitarios/API/PostgreSQL/addon están escritos, pero su ejecución real,
Ruff, mypy, regresión del service y addon Odoo 18 install/update siguen
pendientes. Por tanto M7-05 todavía no se considera cerrado ni habilita M7-06.

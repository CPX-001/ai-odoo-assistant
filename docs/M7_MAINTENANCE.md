# M7 Maintenance operations

M7-05 añade una superficie administrativa pequeña y explícita para mantener el
piloto desde Odoo sin convertir el Assistant en un executor genérico del host.
Browser/Owl continúa hablando únicamente con Odoo; Odoo deriva el actor desde
`env.uid`/base de datos y el Assistant sólo acepta las llamadas server-to-server
autenticadas con la machine credential existente.

## Catálogo cerrado

No existe un endpoint `run`, un nombre de operación enviado por el browser ni un
payload de comando. Las únicas operaciones mutables del catálogo son las rutas
explícitas siguientes:

| Operación | Endpoint | Ejecución | Side effects permitidos |
| --- | --- | --- | --- |
| `readiness_test` | `POST /v1/admin/maintenance/readiness/test` | directa | sólo lectura + audit Assistant |
| `source_rescan` | `POST /v1/admin/maintenance/source/rescan` | job | reconstruye sólo el índice source del Assistant |
| `source_test` | `POST /v1/admin/maintenance/source/test` | directa | evidence/test bounded existente + audit |
| `logs_test` | `POST /v1/admin/maintenance/logs/test` | directa | lectura bounded del provider autorizado + audit |
| `knowledge_reindex` | `POST /v1/admin/maintenance/knowledge/reindex` | job | reingesta sólo knowledge configurado en Assistant DB |
| `reasoning_test` | `POST /v1/admin/maintenance/reasoning/test` | directa | handshake/readiness Codex + audit |
| `action_self_test` | `POST /v1/admin/maintenance/action/self-test` | directa | comprueba authority + tablas Assistant; **no ejecuta business actions** |
| `configuration_revalidate` | `POST /v1/admin/maintenance/configuration/revalidate` | directa | revalida snapshot M7; no aplica ni amplía configuración |

Además existen dos vistas read-only:

- `GET /v1/admin/maintenance/status`: último evento de cada operación y jobs activos;
- `GET /v1/admin/maintenance/jobs/{job_id}`: estado bounded de un job conocido.

Todas las respuestas usan contracts cerrados: state, result code allowlisted,
timestamps y counters. No contienen paths físicos, excerpts, exception text,
secretos ni metadata arbitraria.

## Jobs y recuperación

Sólo `source_rescan` y `knowledge_reindex` usan jobs persistidos. El estado es
`queued -> running -> succeeded|failed`; se persisten actor Odoo, timestamps,
result code y counters bounded. Un índice parcial de PostgreSQL impide dos jobs
activos de la misma operación.

Los jobs activos con más de 15 minutos se consideran abandonados al intentar un
nuevo enqueue y pasan a `failed / maintenance_job_abandoned`, dejando audit. No
se expone cancelación porque las operaciones actuales no tienen una cancelación
transaccional fiable que mejore la seguridad del piloto.

La ejecución background es deliberadamente mínima, no un framework universal de
jobs. Si el proceso cae, el job persistido no desaparece y puede recuperarse por
retry tras la ventana de abandono.

## Source

El rescan reutiliza el scanner existente y sus budgets. Sólo trabaja sobre roots
ya resueltos/autorizados; M7-05 no añade paths nuevos ni amplía filesystem
authority. El resultado administrativo conserva únicamente módulos/ficheros/stale
counts bounded.

## Knowledge

El reindex reutiliza `KnowledgeIngestionService`, el store PostgreSQL existente y
`ODOO_AI_KNOWLEDGE_SOURCES`; M7-05 no introduce otra fuente de paths. Para una
operación administrativa se aceptan como máximo 16 providers configurados y se
mantienen los límites por provider existentes, con 10 s de scan por provider.

Todos los providers se ejecutan dentro de una única transacción de ingestión. Si
un provider devuelve snapshot incompleto o issues, la transacción se revierte y
el índice anterior permanece utilizable. Repetir un rebuild completo conserva la
semántica incremental/idempotente de M5.

## Codex y ACTION

`reasoning_test` reutiliza el readiness handshake de Codex y sólo devuelve uno de
los códigos conocidos (`operational`, auth unavailable, runtime missing,
protocol incompatible, etc.). No devuelve output raw de Codex.

`action_self_test` no crea preview, approval, authority one-shot ni commit. Sólo:

1. comprueba que la authority host-owned puede cargarse por el Assistant;
2. comprueba que las tablas Assistant-side de ACTION existen.

Por tanto un self-test no escribe datos de negocio Odoo ni amplía la allowlist de
M6.

## Configuración

`configuration_revalidate` vuelve a resolver el snapshot efectivo contra los
boundaries HOST_ONLY actuales. No aplica overrides, no modifica `os.environ`, no
reinicia servicios y no destruye la última configuración válida.

## Audit y UI

Cada operación directa escribe un evento final en `maintenance_audit_event`. Los
jobs escriben eventos queued/running/final y su estado en `maintenance_job`.
M7-05 muestra desde Odoo sólo el último resultado y los jobs activos; la
observabilidad/retención completa corresponde a M7-06.

Diagnostics incorpora botones explícitos para las ocho operaciones. Los tres
botones source/log ya existentes se redirigen a la superficie maintenance para
no duplicar acciones. El addon vuelve a mapear localmente `operation + state +
result_code`; cualquier texto/campo extra del backend se ignora y un código
incompatible no se renderiza como instrucción confiable.

## Sigue siendo setup-only

M7-05 no intenta resolver desde Odoo:

- instalar/actualizar Codex o modificar su home/executable;
- autenticar Codex interactuando con credenciales del host;
- crear/rotar shared secrets o ACTION authority secrets;
- cambiar permisos de filesystem/logs;
- provisioning PostgreSQL o reparar migraciones con privilegios;
- reiniciar/modificar systemd;
- editar archivos o ejecutar shell/SQL/Python arbitrario.

## Estado de verificación

Código, migración y tests de M7-05 están implementados en `main`, pero el packet
permanece **pending runtime verification** hasta ejecutar Ruff, mypy, targeted
M7-05, PostgreSQL/migrations, regresión del service y addon Odoo 18 install/tests
+ update. M7-01..04 conservan su estado `runtime verified`; M7 global todavía no
es PASS.

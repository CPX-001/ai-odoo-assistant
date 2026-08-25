# ADR-016 — Runtime operacionalmente autocontenido en el addon Odoo

## Estado

Accepted

## Contexto

La arquitectura anterior separa correctamente propuesta, autoridad y ejecución, pero
materializa esa separación como dos aplicaciones operacionales: el addon Odoo y un
Assistant Service con HTTP loopback, FastAPI/Uvicorn, usuario Unix propio, systemd,
rutas `/opt`/`/etc`/`/var/lib`, PostgreSQL propio, SQLAlchemy y Alembic.

Esa topología aumenta de forma desproporcionada la instalación y la operación para un
producto que ya ejecuta sus writes autoritativos dentro de Odoo y cuyo ReasoningEngine
usa Codex App Server como subprocess efímero por stdio. La frontera HTTP y la segunda
base de datos no son la frontera de seguridad esencial: las invariantes reales son la
identidad Odoo, ACL/record rules, schemas efectivos, tools tipadas, policy host-side,
aprobación, commit/verificación y auditabilidad.

La simplificación no puede convertir controllers HTTP de Odoo en workers bloqueados
durante turnos de decenas de segundos ni puede conceder a Codex acceso genérico al ORM.

## Decisión

### 1. Una sola unidad operacional

`odoo_ai_assistant` será la única aplicación administrada para el Assistant. Browser y
OWL sólo hablan con Odoo. El runtime lógico se conserva como módulos internos del
addon:

```text
OWL / RPC
    -> Odoo application/controllers
        -> turn queue + progress
        -> AgentTurnService
            -> retrieval/evidence
            -> typed tools -> Odoo ORM (usuario real, su=False)
            -> policy/approval/execution
            -> ReasoningEngine
                 -> Codex App Server efímero por stdio
```

Desaparecen como requisitos de producto el Assistant Service HTTP, FastAPI/Uvicorn,
`service_url`, machine shared-secret, usuario/grupo `odoo-ai`, unit systemd propia,
segunda DB PostgreSQL, SQLAlchemy, Alembic y bootstrap PostgreSQL del Assistant.

La separación `application/contracts/ports/adapters` se mantiene internamente. El
cambio elimina separación **operacional**, no separación de responsabilidades.

### 2. Persistencia Odoo-native

Conversaciones, mensajes, turns, planes, aprobaciones, receipts/audit, metadata de
scanner/source/retrieval y configuración persistente pasan progresivamente a modelos
Odoo normales. Las tablas pertenecen a la misma base que el addon, pero el runtime no
obtiene por ello acceso SQL arbitrario: toda lógica de producto usa ORM.

Los registros ligados a usuario conservan `user_id`, `company_id` y record rules. Los
jobs técnicos pueden ser inspeccionados por administradores, pero cualquier operación
de negocio reconstruye un `Environment` con el uid/compañías del turn y `su=False`.

No se mantiene una capa SQLAlchemy sobre la base Odoo.

### 3. Turnos largos mediante scheduler nativo de Odoo

Un submit HTTP valida y persiste un `odoo.ai.turn`, solicita ejecución inmediata con un
`ir.cron` dedicado usando `_trigger()` y devuelve sin esperar al modelo. El cron corre
en otra transacción/cursor y reclama turns persistidos de forma idempotente.

El frontend consulta estado/eventos incrementales mediante RPC corto. Esto evita
mantener un worker HTTP ocupado durante 30–120 s y funciona con `workers=0` y con
cron workers multiproceso sin Redis/Celery/RabbitMQ.

Requisitos operacionales:

- debe existir al menos un cron thread/worker habilitado;
- el diagnóstico del addon muestra si el scheduler no puede procesar turns;
- límites Codex se acotan también por los límites efectivos del cron worker;
- un turn `running` abandonado por restart se vuelve recuperable de forma explícita;
- nunca se relanza automáticamente un write de resultado ambiguo sin su semántica de
  idempotencia/recovery existente.

La implementación no usa threads ad-hoc ni conserva un event loop global dentro de
workers Odoo.

### 4. Autoridad in-process

Eliminar HTTP Odoo↔Assistant elimina machine authentication de esa frontera, no la
validación de negocio. Los adapters in-process quedan ligados al `Environment` efectivo
y sólo implementan los mismos ports estrechos de schema/query/preview/commit/verify.

Codex sólo recibe dynamic tools de lectura/preview. Approval, authority, commit y
verification permanecen host-side. No se introducen `sudo()`, SQL libre, shell genérico
ni métodos ORM arbitrarios. Las business actions continúan siendo specs versionadas.

Los tokens creados únicamente para cruzar el antiguo HTTP se eliminan cuando dejan de
tener consumidor. Si durante la migración un contrato interno todavía exige un token,
se usa una capacidad efímera no persistida y no se interpreta como nueva autoridad.

### 5. Codex

Codex continúa siendo un App Server efímero por turno, lanzado mediante
`create_subprocess_exec`/stdio y cerrado de forma acotada. Hereda la identidad Unix del
proceso Odoo; en instalaciones típicas será `odoo:odoo` sin crear otro usuario.

El repositorio oficial de Codex está bajo Apache-2.0 y jurídicamente permite
redistribución cumpliendo sus condiciones. Aun así, este proyecto **no empaqueta el
binario** por defecto: binarios por plataforma/arquitectura, tamaño, actualización,
provenance y supply-chain convertirían el addon en distribuidor de runtimes. Codex se
mantiene como única dependencia host-level prevista.

El addon:

- autodetecta `codex` desde `PATH` o un override administrativo;
- exige fichero ejecutable y path resuelto;
- no descarga binarios automáticamente;
- muestra estado y diagnóstico desde Odoo;
- usa un `CODEX_HOME` bajo el `data_dir` real de Odoo.

### 6. Estado mutable y logging

La raíz mutable es:

```text
<odoo data_dir>/odoo_ai_assistant/
    codex/
    runtime/
    cache/
    source/
```

No se escribe estado mutable dentro del código del addon. Las rutas se crean con la
identidad del proceso Odoo y permisos restrictivos. Logs operacionales normales usan
`logging.getLogger(__name__)` y terminan en el logging normal de Odoo. Sólo artefactos
diagnósticos que realmente lo necesiten pueden vivir bajo `data_dir`.

### 7. Scanner/retrieval/lifecycle

La instalación crea schema/configuración mínima y runtime dirs. Trabajo costoso como
scanner/index inicial se encola después del install transaction. Update y uninstall son
idempotentes y no ejecutan operaciones host privilegiadas.

El scanner conserva roots acotadas y canonicalización anti-symlink. La fuente de roots
pasa de envelopes provisionadas por un bootstrap externo a hechos runtime Odoo
(`addons_path`) más overrides administrativos explícitos. Retrieval conserva filtrado
ACL y no convierte un índice en autoridad.

### 8. Migración del proyecto actual

El proyecto sigue en desarrollo; se prioriza una arquitectura limpia frente a una capa
de compatibilidad permanente.

La migración se ejecuta por bloques:

1. introducir modelos Odoo/runtime paths/diagnósticos sin cortar el servicio;
2. mover chat/turns/planes/aprobaciones/index metadata a Odoo;
3. mover el motor y adapters al addon y sustituir callbacks HTTP por gateways directos;
4. mover ejecución larga a turn queue + cron trigger + polling de progreso;
5. cambiar configuración/UI al runtime embebido;
6. retirar Assistant Service, installer/systemd/DB/migrations/dependencias legacy;
7. actualizar SoT, docs y tests y realizar revisión arquitectónica final.

La compatibilidad legacy sólo puede existir durante estos bloques y debe desaparecer
antes de declarar completada ADR-016.

## Alternativas consideradas

### Mantener el sidecar y ocultarlo con un instalador mejor

Rechazada. Reduce pasos iniciales pero conserva dos procesos, dos lifecycles, dos
persistencias y una frontera HTTP que no aporta autoridad adicional.

### Ejecutar el turn completo dentro del controller

Rechazada. Un subprocess de 30–120 s ocuparía workers HTTP y degradaría Odoo bajo
concurrencia.

### Celery/RQ/Redis/RabbitMQ

Rechazada para el perfil soportado: resolvería job execution añadiendo precisamente la
infraestructura externa que esta decisión pretende eliminar.

### Threads ad-hoc dentro del worker HTTP

Rechazada como mecanismo principal por lifecycle, recovery y diferencias entre
`workers=0` y multiproceso. El scheduler persistente de Odoo ya proporciona una unidad
de ejecución separada.

### Base PostgreSQL separada pero sin servicio HTTP

Rechazada. Mantendría bootstrap, credenciales, migraciones y SQLAlchemy sin una ventaja
suficiente frente a modelos técnicos Odoo bien aislados.

### Empaquetar Codex dentro del addon

Legalmente posible bajo Apache-2.0 si se cumplen licencia/NOTICE, pero rechazado como
default por distribución multiplataforma, actualizaciones y supply-chain. Puede
reconsiderarse como artefacto de distribución específico separado del addon.

## Consecuencias

- Operación normal converge en administrar sólo Odoo y configurar el addon desde Odoo.
- El fallo de Codex afecta a turns del Assistant, no requiere un segundo daemon que
  reiniciar.
- El scheduler Odoo pasa a ser una dependencia funcional explícita para turnos largos.
- La base Odoo contendrá más modelos técnicos; requieren ACL/record rules, retention y
  tests de upgrade/uninstall.
- Se elimina una cantidad importante de código de deployment/transport/storage, pero
  los contracts y servicios de dominio deben sobrevivir al traslado.
- Durante la migración existen temporalmente dos caminos; esa duplicidad es deuda
  transitoria y no estado final aceptable.

## Referencias

- `docs/ARCHITECTURE.md`
- `docs/DEPLOYMENT_CONFIG.md`
- `docs/adr/ADR-014-unified-host-authorized-agent.md`
- `docs/adr/ADR-015-batch-mutations-and-file-ingestion.md`
- `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.1.pdf`
- Odoo 18 `odoo/addons/base/models/ir_cron.py` (`ir.cron._trigger`)
- `https://github.com/openai/codex` (Apache-2.0)

# M7-07 — Install, upgrade y operator handoff

## Contexto

- Requiere Goals A y B verdes.
- M1 ya implementa bootstrap, releases, backups, migrations forward-only y rollback de runtime; M7 no debe sustituirlo por instalación privilegiada desde Odoo.
- El objetivo es que el paso de setup privilegiado a operación cotidiana quede explícito, verificable y cómodo para un técnico.
- El cierre M6 añadió `sale` como dependencia del addon principal para alojar `sale.order.confirm.v1`. M7 debe comprobar si eso es un requisito real del producto o una consecuencia del primer handler curado; no convertir una capability de ejemplo en dependencia global sin justificarlo contra el Source of Truth.

## Objetivo

Cerrar el lifecycle operativo del piloto: fresh install, handoff a Odoo Settings/Diagnostics, upgrade coordinado, rollback/recovery y comprobación de compatibilidad deben ser reproducibles sin editar código ni reconstruir manualmente configuración del deployment.

## Debes implementar

### Handoff de bootstrap

El bootstrap/setup debe producir un resultado/machine-readable handoff sanitizado que permita a Odoo/Assistant conocer, sin secretos:

- runtime version/build;
- config/schema revision;
- endpoint local efectivo;
- capabilities/setup requirements;
- qué valores quedaron host-owned;
- qué pasos administrativos quedan pendientes en Settings/Diagnostics.

No devolver secret contents ni DSNs con credentials.

### Preflight/doctor

Consolidar un `doctor`/preflight reproducible que pueda comprobar antes/después de install/upgrade:

- filesystem/permissions relevantes;
- Assistant DB/migrations;
- service/runtime;
- Odoo endpoint/addon compatibility;
- configured roots/providers;
- reasoning runtime presence/auth status sanitizado;
- action-authority setup state.

Puede ejecutarse desde bootstrap/setup; Odoo sólo consume el resultado sanitizado cuando sea útil.

### Dependency footprint del addon

Auditar las dependencias funcionales del addon principal contra el producto real:

- distinguir dependencias necesarias para que el Assistant exista de módulos necesarios sólo para una capability/business action concreta;
- comprobar específicamente si `sale` debe ser requisito global por Source of Truth o sólo por `sale.order.confirm.v1`;
- si `sale` no es requisito global, mover la integración específica detrás del mínimo boundary correcto (submódulo/adaptador/capability opcional compatible con la arquitectura existente) para que el addon base no fuerce instalar Sales;
- si el Source of Truth sí exige Sales para el piloto soportado, documentar esa decisión explícitamente y probarla como requirement, no como dependencia accidental;
- no resolver optionalidad mediante imports/reflection frágiles o checks de versión dentro de `application`.

El objetivo no es construir un plugin framework nuevo, sino evitar que la primera business action curada defina accidentalmente el footprint funcional de todo el producto.

### Upgrade

Preservar `OPERATIONS_M1.md`:

- release staged antes de activar;
- backup antes de migration pendiente;
- Alembic forward-only normal;
- health/readiness antes del addon handoff;
- config M7 migration/revision compatible;
- Settings overrides preservados o migrados explícitamente;
- rollback runtime sólo con schema compatibility acknowledgement.

### Operator runbook

Actualizar runbook para un técnico real:

1. privileged bootstrap/setup inicial;
2. abrir Odoo Settings y validar overrides;
3. Diagnostics hasta readiness esperado;
4. maintenance cotidiano desde Odoo;
5. upgrade controlado;
6. recuperación/degraded troubleshooting;
7. uninstall sin purge implícito.

## Debes reutilizar

- installer/bootstrap M1;
- `OPERATIONS_M1.md`;
- deployment discovery/overrides;
- config snapshot M7;
- Diagnostics M7;
- business-action registry/capability boundary M6.

## Fuera de scope

- apt/deb/docker packaging universal salvo que el repo ya lo requiera;
- auto-update desde internet;
- root desde Odoo;
- downgrade automático de DB;
- borrar DB/secrets al uninstall;
- framework universal de plugins Odoo;
- Odoo 19.

## Restricciones

- layouts/rutas DEV no son contratos;
- incluir layout non-default real en tests;
- no imprimir secrets en bootstrap/doctor;
- upgrade failure conserva current/backup de forma segura;
- un Odoo admin no puede invocar comandos privilegiados mediante handoff;
- una capability opcional no puede habilitarse si el módulo/modelo requerido no existe realmente.

## Tests obligatorios

- fresh install normal + non-default;
- rerun idempotente;
- handoff sin secrets y consumible por runtime;
- upgrade con migration/backup y settings preservados;
- fallo pre-activation conserva current;
- rollback runtime semantics existentes no regresan;
- doctor healthy/degraded cases;
- uninstall no purga DB/secrets;
- addon install/update compatible;
- dependency-footprint test que demuestre la decisión final sobre `sale` (base sin Sales si se declara opcional, o requisito explícito reproducible si se mantiene obligatorio);
- curated business action sigue registrándose únicamente cuando su dependency contract se cumple;
- suite, Ruff y mypy.

## Acceptance criteria

- setup privilegiado queda separado de operación diaria;
- un técnico puede reproducir install/upgrade/recovery siguiendo el runbook sin editar código;
- Settings/Diagnostics reciben suficiente contexto para operar tras handoff;
- M1 backup/rollback/security semantics permanecen intactas;
- el footprint funcional del addon está justificado por requisitos reales y no por la primera curated action implementada.

## Después

1. Actualiza runbook con comandos reales y placeholders, nunca paths DEV como requisitos.
2. Documenta qué pasos siguen requiriendo privilegios y por qué.
3. Documenta la decisión final sobre dependencias funcionales opcionales, especialmente `sale`.
4. No avances a M7-08 si upgrade puede perder overrides/secrets o si una dependencia funcional global sigue siendo accidental.

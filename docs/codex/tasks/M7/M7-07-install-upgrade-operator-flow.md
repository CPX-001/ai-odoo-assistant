# M7-07 — Install, upgrade y operator handoff

## Contexto

- Requiere Goals A y B verdes.
- M1 ya implementa bootstrap, releases, backups, migrations forward-only y rollback de runtime; M7 no debe sustituirlo por instalación privilegiada desde Odoo.
- El objetivo es que el paso de setup privilegiado a operación cotidiana quede explícito, verificable y cómodo para un técnico.

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
- Diagnostics M7.

## Fuera de scope

- apt/deb/docker packaging universal salvo que el repo ya lo requiera;
- auto-update desde internet;
- root desde Odoo;
- downgrade automático de DB;
- borrar DB/secrets al uninstall;
- Odoo 19.

## Restricciones

- layouts/rutas DEV no son contratos;
- incluir layout non-default real en tests;
- no imprimir secrets en bootstrap/doctor;
- upgrade failure conserva current/backup de forma segura;
- un Odoo admin no puede invocar comandos privilegiados mediante handoff.

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
- suite, Ruff y mypy.

## Acceptance criteria

- setup privilegiado queda separado de operación diaria;
- un técnico puede reproducir install/upgrade/recovery siguiendo el runbook sin editar código;
- Settings/Diagnostics reciben suficiente contexto para operar tras handoff;
- M1 backup/rollback/security semantics permanecen intactas.

## Después

1. Actualiza runbook con comandos reales y placeholders, nunca paths DEV como requisitos.
2. Documenta qué pasos siguen requiriendo privilegios y por qué.
3. No avances a M7-08 si upgrade puede perder overrides o secretos silenciosamente.

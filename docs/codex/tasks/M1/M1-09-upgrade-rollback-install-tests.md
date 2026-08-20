# M1-09 — Upgrade, rollback y pruebas de instalación

## Contexto

- Requiere M1-08 completado y verde.
- El Source of Truth exige actualizar addon/runtime coordinadamente, migraciones Assistant DB forward-only con backup previo y rollback documentado.

## Objetivo

Demostrar que el runtime puede instalarse y actualizarse de forma repetible, y documentar un rollback operativo que no contradiga la política de migraciones forward-only.

## Contratos que NO puedes romper

- bootstrap/systemd/storage/addon implementados en M1;
- versionado interno existente;
- política de no borrar automáticamente Assistant DB al desinstalar addon.

## Debes implementar

- versión/build identificable del runtime y addon si aún no existe un mecanismo suficiente;
- flujo documentado de upgrade coordinado;
- backup previo de la Assistant DB antes de migraciones destructivas o cuando el procedimiento de upgrade lo requiera;
- rollback documentado del runtime/config;
- aclaración explícita de que Alembic es forward-only en operación normal: si un rollback de código no es compatible con schema nuevo, restaurar backup o usar versión compatible; no ejecutar downgrades automáticos sin decisión nueva;
- comportamiento de uninstall: quitar addon/runtime no purga automáticamente `odoo_ai`;
- smoke script/checklist reproducible de fresh install y segunda ejecución;
- pruebas de fallo parcial razonables y recuperación.

## Fuera de scope

- paquete `.deb` de producción completo si el bootstrap actual ya satisface M1;
- updater automático desde Internet;
- HA/blue-green;
- backup scheduler permanente;
- migraciones de features M2+.

## Restricciones

- nunca destruir Assistant DB como mecanismo normal de upgrade;
- no inventar rollback de datos inseguro;
- documentar claramente qué pasos son automáticos y cuáles son recuperación manual excepcional;
- no reiniciar Odoo si el cambio no lo requiere.

## Tests obligatorios

En entorno disposable:

1. fresh install/bootstrap;
2. verificar DB/migrations/systemd/Odoo health;
3. segunda ejecución del bootstrap;
4. simular/update seguro del runtime y verificar health;
5. ejecutar al menos el procedimiento de rollback de código/config que pueda probarse sin destruir datos;
6. verificar que desinstalar addon no borra Assistant DB, si es seguro automatizarlo en DB fixture;
7. suite/lint/type-check.

## Acceptance criteria

- fresh install reproducible;
- upgrade mantiene service y DB coherentes;
- rollback está documentado y no depende de Alembic downgrade automático;
- Assistant DB sobrevive al uninstall del addon salvo purge explícito;
- segunda ejecución sigue siendo idempotente;
- tests verdes.

## Antes de editar

1. Inspecciona cómo versiona actualmente runtime/addon/migrations.
2. Propón el flujo mínimo de upgrade/rollback sin ampliar scope.
3. Señala cualquier caso no verificable en WSL.

## Después

1. Ejecuta los smoke tests posibles.
2. Deja el runbook de upgrade/rollback en la ubicación documental más coherente del repo.
3. Informa qué parte se verificó realmente y cuál queda para un host fresco.
4. No avances a M1-10.

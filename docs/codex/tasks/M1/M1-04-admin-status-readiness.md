# M1-04 — Admin status y readiness de runtime

## Contexto

- Requiere M1-03 completado y verde.
- `/health` ya existe como liveness simple.
- M1 debe ser observable, pero `FULLY_READY` no debe declararse prematuramente: source/logs/Codex pertenecen a milestones posteriores.

## Objetivo

Implementar `GET /v1/admin/status` como vista estructurada y sanitizada del estado real del runtime, DB y migraciones, diferenciándola claramente de `/health`.

## Contratos que NO puedes romper

- `/health` de M1-01;
- storage y tablas de M1-02/M1-03;
- contratos públicos existentes.

## Debes implementar

- `GET /v1/admin/status`;
- checks deterministas de al menos proceso/runtime, acceso a Assistant DB y revision de migraciones;
- lectura/resumen del `instance_profile`/capability snapshot cuando exista;
- payload estable, estructurado y sin secretos;
- estados por componente y errores sanitizados;
- tests para escenarios healthy y fallo de DB/migration mismatch.

Si necesitas un estado global, no inventes que la instalación está `FULLY_READY` mientras falten capabilities obligatorias de milestones posteriores. Prefiere expresar componentes comprobados y pendientes.

## Fuera de scope

- Diagnostics UI completa;
- source/log checks reales;
- Codex check;
- scanner/fingerprint;
- chat/turn endpoints;
- auth de usuario Odoo/delegación.

## Restricciones

- no devolver DSN, passwords, secretos, filesystem sensible ni tracebacks crudos;
- status se basa en evidencia runtime real, no valores hardcoded;
- los fallos deben degradar el status sin tumbar `/health` salvo que el proceso no pueda arrancar.

## Tests obligatorios

- status con DB disponible y migrations head;
- status con DB no disponible;
- status con revision no esperada si puede simularse de forma segura;
- ausencia de secretos en payloads;
- suite, lint, type-check.

## Acceptance criteria

- `/health` sigue siendo liveness simple;
- `/v1/admin/status` explica de forma determinista el estado de runtime/DB/migrations;
- los errores son sanitizados;
- no se declara readiness de capacidades no implementadas;
- tests verdes.

## Antes de editar

1. Inspecciona contracts/API/storage existentes.
2. Resume el payload propuesto y qué datos lo alimentan.
3. Señala si hace falta extender un contrato público.

## Después

1. Ejecuta tests.
2. Muestra ejemplos sanitizados de status healthy y degradado.
3. No avances a M1-05.

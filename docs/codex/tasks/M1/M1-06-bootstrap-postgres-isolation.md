# M1-06 — Bootstrap PostgreSQL e aislamiento de Odoo

## Contexto

- Requiere M1-05 completado y verde.
- El Source of Truth exige una DB `odoo_ai` separada y que el role del Assistant pueda conectar a ella pero no a la DB Odoo.

## Objetivo

Extender el bootstrap para crear/actualizar de forma idempotente la DB y role propios del Assistant, aplicar migraciones y demostrar técnicamente que ese role no puede conectar a la DB Odoo sin romper el acceso normal de Odoo.

## Contratos que NO puedes romper

- storage/migrations de M1-02/M1-03;
- bootstrap foundation de M1-05;
- política de no SQL directo del Assistant Service contra Odoo.

## Debes implementar

- creación idempotente del role `odoo_ai_service` o nombre equivalente ya decidido en el repo;
- creación idempotente de la DB Assistant separada;
- credenciales/config del Assistant fuera del repo;
- ejecución de Alembic `upgrade head` desde bootstrap;
- comprobación automática `CONNECT Assistant DB = YES`;
- comprobación automática `CONNECT Odoo DB = NO` para el role del Assistant;
- mecanismo de aislamiento que preserve el acceso existente de Odoo y sea reproducible;
- tests/smoke de primera y segunda ejecución.

## Precaución específica PostgreSQL

No asumas que revocar privilegios al role basta si `PUBLIC` conserva `CONNECT`. Inspecciona los privilegios/autenticación reales y demuestra el rechazo con una conexión real. No cambies privilegios globales de la DB Odoo de forma disruptiva sólo para pasar el test. Si el mecanismo correcto requiere una decisión arquitectónica que afecte al deployment soportado, detente y señala la necesidad de ADR antes de improvisar.

## Fuera de scope

- acceso a tablas Odoo;
- replicación de datos Odoo;
- pgvector/Redis/otros motores;
- backup automation sofisticada;
- systemd (M1-07).

## Restricciones

- no usar credenciales SQL del role Odoo dentro del Assistant Service;
- cualquier privilegio administrativo PostgreSQL sólo durante bootstrap;
- la credencial runtime resultante debe tener mínimo privilegio;
- nunca imprimir passwords/DSNs completos.

## Tests obligatorios

- bootstrap sobre cluster PostgreSQL de test con DB Odoo existente;
- conexión exitosa como Assistant role a Assistant DB;
- conexión rechazada como Assistant role a DB Odoo;
- Odoo/role legítimo sigue pudiendo conectar tras el cambio;
- `alembic current`/`upgrade head` correcto;
- segunda ejecución idempotente;
- suite, lint/type-check.

## Acceptance criteria

- DB y role Assistant existen con ownership/privilegios mínimos;
- migrations están en head;
- prueba real demuestra que Assistant role NO puede conectar a DB Odoo;
- el acceso normal de Odoo no se rompe;
- repetir bootstrap no duplica ni regenera innecesariamente recursos;
- tests verdes.

## Antes de editar

1. Inspecciona roles, DBs y privilegios del cluster DEV sin modificarlos.
2. Resume el mecanismo de aislamiento propuesto y por qué realmente bloquea `CONNECT`.
3. Si requiere una decisión nueva de arquitectura, detente antes de aplicarla.

## Después

1. Ejecuta las pruebas positivas/negativas de conexión.
2. Informa evidencia sanitizada y cambios realizados.
3. No avances a M1-07.

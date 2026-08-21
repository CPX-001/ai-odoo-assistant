# M1-06 — Bootstrap PostgreSQL e aislamiento de Odoo

## Contexto

- Requiere M1-05 completado y verde.
- El Source of Truth exige una DB Assistant separada y que el role del Assistant no tenga acceso SQL a la DB Odoo.
- El mismo cluster PostgreSQL que Odoo es el **default recomendado** para self-hosted, no una dependencia obligatoria de las interfaces del producto.
- `docs/DEPLOYMENT_CONFIG.md` define la política de configuración del deployment.

## Objetivo

Extender el bootstrap para crear/actualizar de forma idempotente la DB y role propios del Assistant, aplicar migraciones y demostrar técnicamente el aislamiento respecto a Odoo sin romper el acceso normal de Odoo.

## Contratos que NO puedes romper

- storage/migrations de M1-02/M1-03;
- bootstrap foundation de M1-05;
- política de no SQL directo del Assistant Service contra Odoo;
- configuración externa de la Assistant DB mediante DSN/nombre, sin `localhost` hardcodeado como contrato.

## Debes implementar

Para el perfil automatizado por defecto:

- creación idempotente del role `odoo_ai_service` o nombre equivalente decidido/configurado;
- creación idempotente de una DB Assistant separada;
- credenciales/config del Assistant fuera del repo;
- ejecución de Alembic `upgrade head` desde bootstrap;
- comprobación automática de conexión a la Assistant DB;
- si Assistant y Odoo comparten cluster, comprobación automática de que el role Assistant no puede conectar a la DB Odoo;
- mecanismo de aislamiento que preserve el acceso existente de Odoo y sea reproducible;
- tests/smoke de primera y segunda ejecución.

Además:

- el host/puerto/nombre/DSN de PostgreSQL del Assistant deben proceder de configuración, discovery o defaults sustituibles, no de constantes de application;
- no asumir que `db_host` de Odoo es `localhost`;
- no asumir que la Assistant DB debe residir necesariamente en el mismo host/cluster: si se configura un PostgreSQL externo existente y el bootstrap no puede administrarlo, debe existir un camino de configuración/manual fallback accionable en vez de reescribir la arquitectura;
- las interfaces storage/runtime deben funcionar igual independientemente de que la DB Assistant esté local o remota.

## Precaución específica PostgreSQL

No asumas que revocar privilegios al role basta si `PUBLIC` conserva `CONNECT`. Inspecciona los privilegios/autenticación reales y demuestra el rechazo con una conexión real cuando ambas DB están en el mismo cluster.

No cambies privilegios globales de la DB Odoo de forma disruptiva sólo para pasar el test. Si el mecanismo correcto requiere una decisión arquitectónica que afecte al deployment soportado, detente y señala la necesidad de ADR antes de improvisar.

Cuando Odoo y Assistant estén en clusters distintos, el aislamiento no debe simularse con una prueba irrelevante: documenta qué boundary impide al Assistant recibir credenciales/acceso a Odoo y qué parte puede verificarse automáticamente.

## Fuera de scope

- acceso a tablas Odoo;
- replicación de datos Odoo;
- pgvector/Redis/otros motores;
- backup automation sofisticada;
- systemd (M1-07);
- automatización universal de proveedores PostgreSQL gestionados.

## Restricciones

- no usar credenciales SQL del role Odoo dentro del Assistant Service;
- cualquier privilegio administrativo PostgreSQL sólo durante bootstrap/setup;
- la credencial runtime resultante debe tener mínimo privilegio;
- nunca imprimir passwords/DSNs completos;
- no codificar el cluster/host DEV como requisito del storage package;
- cambiar DB/host del Assistant no debe requerir editar Python.

## Tests obligatorios

En el perfil default con cluster PostgreSQL de test y DB Odoo existente:

- conexión exitosa como Assistant role a Assistant DB;
- conexión rechazada como Assistant role a DB Odoo;
- Odoo/role legítimo sigue pudiendo conectar tras el cambio;
- `alembic current`/`upgrade head` correcto;
- segunda ejecución idempotente.

Además:

- test de settings con host/puerto/nombre de Assistant DB no-default;
- test que demuestre que storage construye la conexión desde configuración externa;
- si existe modo external-existing, smoke que no intente administrar el cluster cuando no tiene privilegios;
- suite, lint/type-check.

## Acceptance criteria

- DB y role Assistant existen con ownership/privilegios mínimos en el perfil automatizado;
- migrations están en head;
- prueba real demuestra que Assistant role NO puede acceder a Odoo DB en el escenario same-cluster;
- el acceso normal de Odoo no se rompe;
- repetir bootstrap no duplica ni regenera innecesariamente recursos;
- host/puerto/nombre/DSN del Assistant no están acoplados al entorno DEV;
- un PostgreSQL Assistant explícito distinto del default puede configurarse sin modificar código, aunque un proveedor externo pueda requerir fallback administrativo manual;
- tests verdes.

## Antes de editar

1. Inspecciona roles, DBs, endpoints y privilegios del entorno DEV sin modificarlos.
2. Resume qué partes son defaults del perfil y cuáles son contratos generales.
3. Resume el mecanismo de aislamiento propuesto y por qué realmente bloquea acceso a Odoo.
4. Si requiere una decisión nueva de arquitectura, detente antes de aplicarla.

## Después

1. Ejecuta las pruebas positivas/negativas de conexión aplicables.
2. Informa evidencia sanitizada y cambios realizados.
3. Enumera cualquier assumption de topología PostgreSQL que permanezca y justifícala.
4. No avances a M1-07.

# M1-02 — PostgreSQL, SQLAlchemy y Alembic

## Contexto

- Requiere M1-01 completado y verde.
- Lee las instrucciones raíz/locales y `docs/codex/tasks/M1/README.md`.
- La DB del Assistant es PostgreSQL separada de la DB Odoo.
- `docs/DEPLOYMENT_CONFIG.md` exige que endpoint/nombre de la Assistant DB sean configuración, no topología hardcodeada.

## Objetivo

Crear la infraestructura mínima de persistencia del Assistant Service con SQLAlchemy + Alembic, conectada exclusivamente a su propia DB y preparada para migraciones reproducibles.

## Contratos que NO puedes romper

- contracts y ports de M0;
- API `/health` de M1-01;
- dependency boundaries.

## Debes implementar

- dependencias SQLAlchemy y Alembic;
- configuración de conexión a la DB Assistant sin credenciales hardcoded;
- host/puerto/usuario/nombre de DB derivados del DSN/configuración externa, sin asumir `localhost` dentro de storage;
- nombre esperado de la Assistant DB configurable, con `odoo_ai` como default razonable;
- engine/session lifecycle o equivalente mínimo;
- estructura `storage` y `migrations/` coherente con el repo;
- baseline Alembic ejecutable;
- prueba de conexión/migración contra PostgreSQL de test;
- mecanismo claro para identificar que la URL apunta a la DB Assistant.

Todavía no añadas las tablas funcionales de M1-03 salvo metadata técnica estrictamente necesaria por Alembic.

## Fuera de scope

- acceso SQL a la DB Odoo;
- tablas de conversaciones/scanner/RAG/approvals;
- `/v1/admin/status`;
- installer/systemd;
- addon Odoo;
- automatización de creación de clusters PostgreSQL externos.

## Restricciones

- nunca reutilizar credenciales SQL de Odoo para el service;
- secretos sólo por configuración externa apropiada, nunca repo/prompts/logs;
- `contracts` no depende de SQLAlchemy/Alembic;
- no introducir repositorios genéricos ni ORM abstractions especulativas;
- cambiar de host/puerto/nombre de Assistant DB no debe requerir editar Python.

## Tests obligatorios

- suite existente;
- test de conexión a PostgreSQL Assistant de test;
- configuración con DB/host no-default o URL construida para un endpoint alternativo;
- rechazo de backend que no sea PostgreSQL y de URL que apunte a una DB distinta de la esperada;
- `alembic upgrade head` desde DB vacía;
- segunda ejecución de `alembic upgrade head` sin cambios/errores;
- lint/type-check.

## Acceptance criteria

- DB Assistant vacía puede migrarse a `head`;
- repetir migración es estable;
- el código de storage no necesita ni conoce una URL de DB Odoo;
- endpoint/nombre de Assistant PostgreSQL son configurables externamente;
- configuración sensible no aparece en Git ni logs;
- tests verdes.

## Antes de editar

1. Inspecciona el layout y configuración dejados por M1-01.
2. Explica brevemente dónde vivirán engine/session/migrations.
3. Distingue defaults DEV de settings de deployment.
4. Señala conflictos si los hay.

## Después

1. Ejecuta tests y migraciones reales contra DB de test.
2. Informa comandos usados y evidencia del resultado.
3. Lista cualquier endpoint/path de DB fijado en código y elimínalo o justifica por qué no pertenece al cliente.
4. No avances a M1-03.

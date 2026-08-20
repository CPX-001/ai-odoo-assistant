# M1-01 — FastAPI runtime y health

## Contexto

- M0 debe haber terminado con PASS.
- Lee `AGENTS.md`, `service/AGENTS.md`, `tests/AGENTS.md`, `docs/ARCHITECTURE.md` y `docs/codex/tasks/M1/README.md`.
- Inspecciona el package y contratos reales creados en M0 antes de decidir nombres o paths.

## Objetivo

Arrancar localmente el Assistant Service como una aplicación FastAPI mínima y obtener una respuesta determinista de `/health` sin introducir storage, Odoo, Codex ni lógica de producto.

## Contratos que NO puedes romper

- `service/src/odoo_ai/contracts/**`
- ports creados en M0
- reglas de dependencia de `docs/ARCHITECTURE.md`

## Debes reutilizar

- package/toolchain de M0;
- patrones de configuración ya existentes si M0 los creó;
- contratos existentes en lugar de duplicar DTOs.

## Debes implementar

- dependencia FastAPI y servidor ASGI mínimo necesario;
- módulo `api`/entrypoint siguiendo el layout real del repo;
- app factory o estructura equivalente testeable;
- `GET /health` con respuesta estructurada, estable y sin secretos;
- comando documentado para arrancar el service en DEV sobre loopback;
- unit/API tests del endpoint.

`/health` sólo debe demostrar que el proceso HTTP está vivo. La comprobación de DB/migraciones/readiness completo pertenece a tareas posteriores.

## Fuera de scope

- `/v1/admin/status`;
- SQLAlchemy/Alembic/PostgreSQL;
- systemd/installer;
- addon Odoo;
- autenticación/delegación;
- scanner/source/logs;
- Codex/agent loop/RAG;
- websockets/SSE.

## Restricciones

- `contracts` no puede importar FastAPI;
- `application` no debe acoplarse al framework HTTP;
- no secretos ni configuración sensible en respuestas/logs;
- bind DEV explícito a `127.0.0.1`, no `0.0.0.0` por defecto.

## Tests obligatorios

Ejecuta los comandos reales definidos por el repo para:

- tests de M0 completos;
- tests API de `/health`;
- lint;
- type-check.

## Acceptance criteria

- el service arranca desde el package instalado/editable;
- `GET /health` devuelve 200 y payload estable;
- el endpoint no depende de una DB ni de Odoo para responder;
- ningún contrato de M0 se acopla a FastAPI;
- tests/lint/type-check verdes.

## Antes de editar

1. Resume el estado real relevante del repo.
2. Indica el entrypoint/layout que vas a usar y por qué encaja con M0.
3. Señala cualquier conflicto con el Source of Truth.

## Después

1. Ejecuta verificaciones.
2. Informa archivos cambiados y comando exacto de arranque DEV.
3. No avances a M1-02.

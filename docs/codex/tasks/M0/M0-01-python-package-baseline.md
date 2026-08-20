# PROMPT CODEX — M0-01 Python package baseline

## Contexto

- Lee `AGENTS.md`, `service/AGENTS.md`, `tests/AGENTS.md`, `docs/ARCHITECTURE.md` y `docs/codex/tasks/M0/README.md`.
- Inspecciona el repo real antes de modificar.
- El bootstrap documental ya existe; esta es la primera task de implementación de M0.

## Objetivo

Crear la baseline mínima del package Python del Assistant Service y su toolchain, sin implementar ninguna feature del producto.

## Contratos que NO puedes romper

- `contracts` no puede depender de FastAPI, Odoo, Codex ni storage.
- No introducir checks de major de Odoo en `application`.
- Mantener el layout previsto en el Source of Truth: `service/src/odoo_ai/...`.

## Debes implementar

- `service/pyproject.toml`.
- Package `service/src/odoo_ai/` importable.
- Subpackages vacíos/mínimos necesarios para preparar M0: `contracts/` y, si hace falta para las siguientes tasks, `ports/` o equivalente pequeño y explícito.
- Configuración mínima de `pytest`, `ruff` y `mypy` en `pyproject.toml` o archivos equivalentes justificados.
- Un smoke test que demuestre que el package puede importarse.

Dependencias de runtime permitidas en esta task: sólo las estrictamente necesarias para contratos M0; preferir `pydantic>=2`. No añadir FastAPI, SQLAlchemy, Alembic, psycopg, Codex clients ni Odoo libraries todavía.

## Fuera de scope

- Contratos funcionales completos.
- Ports funcionales.
- FastAPI.
- PostgreSQL y migrations.
- Addon Odoo.
- Scanner, retrieval, logs o Codex.
- CI remoto o Docker.

## Tests obligatorios

Ejecuta desde el entorno WSL real los comandos apropiados del proyecto, equivalentes a:

```bash
pytest
ruff check .
mypy service/src
```

Si la ubicación del virtualenv o comandos actuales difiere, adapta los comandos sin cambiar el objetivo y documenta exactamente qué ejecutaste.

## Acceptance criteria

- `service/pyproject.toml` existe y el package usa layout `src/`.
- `import odoo_ai` funciona en el entorno de desarrollo.
- Existe al menos un smoke test verde.
- `pytest`, `ruff` y `mypy` pasan para el scope existente.
- No se han añadido dependencias o features de M1+.
- No hay imports desde `odoo`, FastAPI, Codex o storage en `contracts`.

## Antes de editar

1. Resume en pocas líneas el estado real del repo y del entorno Python disponible.
2. Indica cualquier conflicto con el Source of Truth.
3. Si no hay conflicto, implementa sin ampliar scope.

## Después

1. Ejecuta las verificaciones.
2. Informa archivos cambiados y comandos ejecutados.
3. Señala riesgos o decisiones pendientes.
4. No continúes con M0-02 automáticamente.

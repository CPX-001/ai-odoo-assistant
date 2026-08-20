# PROMPT CODEX — M0-02 Core contracts

## Contexto

- Ejecutar después de M0-01 verde.
- Lee `AGENTS.md`, `service/AGENTS.md`, `tests/AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/codex/tasks/M0/README.md` y el código real creado en M0-01.
- Usa como fuente de verdad los contratos conceptuales de §§6.2, 24 y 24.1 del Source of Truth.

## Objetivo

Implementar los contratos base más deterministas y estables: `ScreenContext`, `RecordRef` y `Evidence`, con Pydantic v2 y tests unitarios.

## Contratos que NO puedes romper

- `contracts` sólo depende de stdlib + Pydantic.
- `ScreenContext` no contiene identidad confiada desde browser.
- `Evidence` conserva `kind`, `status`, `provenance/pointer`, sensibilidad y fingerprint según la especificación.
- No añadir comportamiento de ORM, filesystem, DB ni networking.

## Debes implementar

En `service/src/odoo_ai/contracts/`, nombres exactos de fichero/clase pueden variar si el diseño es más limpio, pero deben existir responsabilidades equivalentes a:

- `ScreenContext`:
  - `action_id: int | None`
  - `menu_id: int | None`
  - `view_type: str | None`
  - `model: str | None`
  - `res_id: int | None`
  - `selected_ids: list[int]`
  - `allowed_context_subset: dict[str, ...]` con tipo razonablemente seguro/serializable
  - `captured_at: datetime`
- `RecordRef`:
  - `model: str`
  - `id: int`
  - `display_name: str | None`
- `Evidence` según §24.1:
  - UUID
  - kind
  - status
  - title
  - summary
  - payload
  - pointer opcional
  - observed_at opcional
  - sensitivity
  - fingerprint opcional

Usa `Enum`/`Literal` sólo donde aporte claridad y JSON Schema estable; evita una jerarquía sofisticada de clases.

Añade tests para:

- construcción válida;
- serialización JSON;
- defaults seguros (listas/dicts no compartidos);
- rechazo de valores fuera de enums/literals;
- timezone/datetime serializable sin inventar políticas adicionales.

## Fuera de scope

- UserExecutionContext/DelegationContext completo.
- ModelSchema/FieldSpec.
- ContextPack.
- ToolSpec.
- AnswerEnvelope.
- ORM/OdooGateway.
- Persistencia.

## Tests obligatorios

```bash
pytest
ruff check .
mypy service/src
```

## Acceptance criteria

- Los tres contratos están implementados, documentados de forma breve y exportados desde `odoo_ai.contracts`.
- Pueden serializarse y producir JSON Schema válido.
- No contienen dependencias prohibidas.
- Tests cubren tipos y defaults relevantes.
- No existe lógica de negocio o infraestructura dentro de los modelos.

## Antes de editar

1. Inspecciona los contratos existentes; no dupliques tipos ya creados.
2. Señala desviaciones del Source of Truth.
3. Implementa sólo el scope autorizado.

## Después

1. Ejecuta tests/lint/type-check.
2. Resume archivos cambiados y cualquier decisión de naming/tipos.
3. No continúes con M0-03 automáticamente.

# PROMPT CODEX — M0-04 Ports

## Contexto

- Ejecutar después de M0-03 verde.
- Lee `AGENTS.md`, `service/AGENTS.md`, `docs/ARCHITECTURE.md`, el Source of Truth y el código real.
- Los ports son fronteras estables; no implementes adapters concretos.

## Objetivo

Definir los ports mínimos de M0: `ReasoningEngine`, `OdooGateway` y `LogProvider`, con contratos pequeños, testeables y sin acoplar application a tecnologías concretas.

## Contratos que NO puedes romper

- `ReasoningEngine` no conoce ORM, filesystem/log providers concretos ni detalles de transporte Odoo.
- `OdooGateway` representa capacidades acotadas; no expone `execute_kw`, `execute_method` ni método genérico arbitrario.
- `LogProvider` ofrece lectura/búsqueda acotada; no recibe shell commands ni instrucciones libres del modelo.
- Ports dependen de contracts + stdlib/typing, no de FastAPI, Odoo, Codex, SQLAlchemy ni storage concreto.

## Debes implementar

### `ReasoningEngine`

Usar `Protocol` async con responsabilidad equivalente a §14.1:

```python
async def run_turn(
    self,
    context: ContextPack,
    tools: list[ToolSpec],
    output_schema: dict,
) -> AnswerEnvelope: ...
```

No añadir selección multi-provider ni lifecycle complejo.

### `OdooGateway`

En M0 sólo debe fijar una frontera mínima y segura para futuras lecturas/runtime metadata. Diseña un `Protocol` pequeño que permita evolucionar hacia M2 sin exponer superficie arbitraria.

No implementar todavía comunicación con Odoo. Si para tipar métodos hacen falta request/result contracts mínimos, créalos sólo si son imprescindibles y explica por qué.

### `LogProvider`

Protocol mínimo alineado con §17: búsqueda acotada y recuperación de traceback/ref cuando corresponda. No implementar FileLogProvider/JournalLogProvider todavía.

## Ubicación

Preferir una ubicación clara como `service/src/odoo_ai/ports/` o una equivalente que respete las dependency rules. No esconder ports dentro de adapters concretos.

## Fuera de scope

- CodexAppServerEngine.
- Odoo RPC/HTTP adapter.
- FileLogProvider/JournalLogProvider.
- ToolExecutor.
- Runtime schemas reales.
- FastAPI.
- Storage.

## Tests obligatorios

Añade tests estructurales/smoke cuando aporten valor: imports, Protocols runtime-checkable sólo si existe una razón real, y fakes mínimos para demostrar sustituibilidad. Evita tests triviales de `Protocol` que no prueben nada útil.

Ejecuta:

```bash
pytest
ruff check .
mypy service/src
```

## Acceptance criteria

- Existen los tres ports y están exportados desde un namespace claro.
- Ninguno importa tecnologías/adapters prohibidos.
- `ReasoningEngine` conserva el contrato conceptual del Source of Truth.
- `OdooGateway` no contiene ejecución arbitraria.
- `LogProvider` no expone shell/filesystem libre.
- No hay implementations concretas.
- Suite verde.

## Después

Resume las firmas finales y cualquier desviación de naming respecto al Source of Truth. No continúes con M0-05 automáticamente.

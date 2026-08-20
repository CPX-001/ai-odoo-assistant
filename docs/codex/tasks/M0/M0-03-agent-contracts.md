# PROMPT CODEX — M0-03 Agent contracts

## Contexto

- Ejecutar después de M0-02 verde.
- Lee las instrucciones aplicables y el código real existente.
- Usa como base §§15.4, 24 y 24.2 del Source of Truth.

## Objetivo

Completar los contratos mínimos que permiten describir un turn agéntico sin implementar el agent loop: `ContextPack`, `ToolSpec` y `AnswerEnvelope`, más los tipos auxiliares estrictamente necesarios.

## Contratos que NO puedes romper

- `contracts` sigue limitado a stdlib + Pydantic.
- `AnswerEnvelope.evidence_refs` sólo referencia IDs; no debe inventar ni resolver evidencia.
- `ToolSpec` describe una tool pero no autoriza su ejecución.
- `ContextPack` es datos normalizados, no un contenedor de servicios/adapters.

## Debes implementar

Responsabilidades equivalentes a:

### `ToolSpec`

- nombre estable;
- descripción;
- `input_schema: dict`;
- riesgo/tipo de operación;
- identificador de executor o referencia equivalente simple.

No construir un plugin framework ni decorators/registries complejos.

### `AnswerEnvelope`

Según §24.2:

- `answer_markdown: str`
- workflow: `HOW_TO | QUERY | EXPLAIN | DIAGNOSE | ACTION`
- confidence: `high | medium | low`
- `evidence_refs: list[UUID]`
- `limitations: list[str]`
- `proposed_action` opcional

Para `proposed_action`, si los contratos WritePreview/BusinessActionPreview aún no existen, usa una representación mínima explícita que no congele prematuramente el diseño de M6. Documenta la decisión. No implementes writes.

### `ContextPack`

Representa las responsabilidades de §15.4. Debe reutilizar `ScreenContext` y `Evidence`. Los tipos auxiliares que aún no tengan contrato final (`UserRequest`, `UserExecutionContext`, `InstanceProfileSummary`, `ConversationState`, `TurnLimits`, workflow hint) pueden modelarse como contratos mínimos explícitos si son necesarios para mantener tipado útil y JSON Schema estable.

Regla: crear sólo los auxiliares necesarios para que `ContextPack` no sea un `dict[str, Any]` gigante. No anticipar todas las features futuras.

## Fuera de scope

- `ToolCall`/`ToolResult` ejecutables.
- Tool registry.
- EffectiveRequestPolicy completa.
- Runtime schemas.
- Writes/approvals.
- Agent loop.
- Codex adapter.

## Tests obligatorios

- construcción/serialización de `ContextPack`;
- validación de workflow/confidence/risk;
- referencias UUID de evidencia;
- JSON Schema de los contratos públicos;
- suite completa `pytest`, `ruff`, `mypy`.

## Acceptance criteria

- `ContextPack`, `ToolSpec` y `AnswerEnvelope` están exportados públicamente.
- Los contratos son suficientemente tipados para que un adapter futuro no dependa de dicts arbitrarios en las fronteras principales.
- No existe lógica de autorización dentro de `ToolSpec`.
- No se ha implementado ejecución de tools ni ReasoningEngine.
- Tests/lint/type-check verdes.

## Antes de editar

Inspecciona lo creado en M0-01/M0-02 y minimiza nuevos tipos. Si el Source of Truth deja un nombre exacto abierto, prioriza responsabilidad y simplicidad.

## Después

Documenta cualquier auxiliar introducido y por qué era necesario. No continúes con M0-04 automáticamente.

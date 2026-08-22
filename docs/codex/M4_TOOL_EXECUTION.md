# M4 tool execution boundary

## M4-03: executor y evidence ledger

`odoo_ai.tools` es una capa host-controlled y no conoce Codex, SQLAlchemy,
Odoo ni paths del deployment. Cada turn construye explícitamente un
`ToolRegistry` a partir de bindings concretos:

```python
registry = ToolRegistry([
    RegisteredTool(
        spec=echo_spec,
        executor_id="fixture.echo.v1",
        input_model=EchoInput,
        output_model=EchoOutput,
        handler=echo_handler,
        max_calls=4,
    )
])
```

No existe discovery, reflection, import por nombre ni `getattr`. El
`executor_id` y el JSON schema del `ToolSpec` deben coincidir con el binding
construido por el host; sólo se admiten riesgos `read` y `metadata`.

Orden de validación:

```text
call id no repetido
  -> tool registrada
  -> risk permitido
  -> nesting + bytes de input
  -> Pydantic input exacto
  -> deadline + budgets de calls
  -> handler explícito
  -> Pydantic output + Evidence
  -> bytes de output
  -> commit atómico en EvidenceLedger
```

Errores del handler se reducen a códigos técnicos; exceptions, argumentos y
outputs crudos no atraviesan el boundary.

## Budgets elegidos

Los defaults server-side por turn son:

| Budget | Default | Motivo |
|---|---:|---|
| calls totales | 12 | suficiente para el slice source sin loop abierto |
| input total | 64 KiB | inputs son refs y búsquedas pequeñas |
| output total | 256 KiB | permite candidatos y excerpts acotados |
| nesting de input | 8 | acepta schemas normales y bloquea payloads patológicos |
| deadline total | 30 s | evita ocupar el worker indefinidamente |
| input por tool | 16 KiB | default conservador, sustituible por binding |
| output por tool | 96 KiB | soporta resultados source sin respuestas gigantes |
| calls por tool | 4 | limita repetición incluso si queda budget total |
| Evidence items | min(`TurnLimits.max_evidence_items`, 24) | el límite del turn nunca puede ampliarse |
| bytes de Evidence | 192 KiB | limita lo reenviado al engine |

Cada binding puede reducir, pero no ampliar silenciosamente, los caps agregados.
`TurnLimits.max_tool_calls` se cruza con el máximo server-side y el menor gana.

## Evidence ledger

El ledger existe sólo durante el turn. Conserva por separado Evidence `live` y
`retrieved`, indexa por UUID y acepta un UUID repetido únicamente si el contenido
canónico es idéntico. Cap de items, cap de bytes y conflictos se validan antes de
modificarlo, por lo que una inserción múltiple es atómica.

La resolución final de `AnswerEnvelope.evidence_refs` consulta este índice. Un
UUID inventado produce `evidence_ref_unknown`; el texto del modelo nunca crea
Evidence.

## M4-04: catálogo source

El contrato estable conserva tres nombres lógicos, todos construidos desde los
schemas Pydantic reales de M3:

| Nombre lógico | Input | Output validado |
|---|---|---|
| `source.find_symbol` | `FindSymbolRequest` | `FindSymbolResult` |
| `source.find_model_extensions` | `FindModelExtensionsRequest` | `FindModelExtensionsResult` |
| `source.read_excerpt` | `ReadExcerptRequest` | `ReadExcerptToolData` + `Evidence(source)` |

No se publican tools de rescan, roots, glob, grep, lectura de fichero, listado,
shell ni diagnostics. Los inputs tienen `extra=forbid`; `read_excerpt` sólo
acepta una `SourceRef` indexada y vuelve a comprobar root y fingerprint. Un ref
manipulado o stale devuelve un error explícito y no entra como Evidence checked.

El wiring por turn obtiene el inventory actual, aplica la selección de roots de
M3 (override explícito antes que roots confirmados), abre una única sesión del
Assistant DB en un worker dedicado y la cierra junto con su engine. Ni
`application` ni el modelo reciben SQLAlchemy, roots físicos o paths libres.

## Bridge dinámico Codex 0.149

La Responses API usada por App Server exige nombres con
`^[a-zA-Z0-9_-]+$`. El adapter traduce exclusivamente en el transporte:

| Contrato lógico | Alias App Server |
|---|---|
| `source.find_symbol` | `source_find_symbol` |
| `source.find_model_extensions` | `source_find_model_extensions` |
| `source.read_excerpt` | `source_read_excerpt` |

La traducción inversa ocurre antes de crear el `ToolCall`; collisions, nombres
desconocidos y specs alteradas fallan cerrados. El request experimental probado
es `item/tool/call` con `threadId`, `turnId`, `callId`, `tool` y `arguments`. La
respuesta correlacionada tiene `success` y un único `contentItems` de tipo
`inputText` cuyo texto es JSON canónico y acotado. Toda ejecución sigue pasando
por `ToolExecutor`; el adapter no llama handlers directamente.

El fake App Server cubre la secuencia
`find_model_extensions -> find_symbol -> read_excerpt`, cita la Evidence
comprobada y verifica que no sale el root físico. El smoke opt-in
`tests/integration/test_codex_dynamic_tools_smoke.py` pasó el 2026-08-22 con
`@openai/codex 0.149.0` y `gpt-5.6-sol`: el modelo solicitó exactamente una tool
registrada y el resultado volvió al mismo turn. La autenticación permaneció
gestionada por Codex; el test no leyó ni copió tokens.

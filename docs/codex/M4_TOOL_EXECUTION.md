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

# M5-04 — Dynamic tools y workflow QUERY

## Contexto

- Requiere M5-03 verde.
- M4 ya dispone de `ReasoningEngine`, dynamic tools, `ToolExecutor` y EvidenceLedger.
- Esta task debe reutilizar esas boundaries; no crear un segundo agent loop específico para QUERY.

## Objetivo

Conectar las primitives ORM de M5-03 al agent loop como tools read-only allowlisted y cerrar un workflow `QUERY` completo con salida/citas validadas.

## Contratos que NO puedes romper

- `ReasoningEngine.run_turn`;
- `ToolExecutor` conserva autoridad server-side;
- `ToolSpec` describe, no autoriza;
- no proposed actions en M5;
- browser sigue fuera del Assistant Service.

## Debes implementar

### Tools QUERY

Define bindings explícitos, con nombres/schemas estables y estrechos, equivalentes a:

- `odoo.get_effective_schema` cuando haga falta discovery de fields;
- `odoo.query_records`;
- `odoo.aggregate_records`.

Cada binding:

- usa input Pydantic exacto;
- cruza args con schema efectivo y autoridad del turn;
- mantiene caps propios y agregados de `ToolExecutor`;
- devuelve sólo resultados normalizados + Evidence checked;
- no acepta model/method/domain/order libres fuera del contrato.

### Workflow QUERY

Añade contratos request/response y application service separados de `ExplainService` que:

1. valida contexto/autoridad;
2. prepara `ContextPack` con `workflow_hint=QUERY`;
3. añade Evidence/schema inicial sólo cuando sea necesaria;
4. construye registry QUERY explícito;
5. ejecuta Codex mediante el engine existente;
6. recoge ToolExecutionReport/Evidence;
7. valida `AnswerEnvelope` y citas;
8. produce response browser-facing sanitizada a través de Odoo.

No conviertas `ExplainService` en un orchestrator universal si eso mezcla reglas de evidencia distintas.

### Validación de respuesta

- `workflow == QUERY`;
- `proposed_action is None`;
- refs sólo a Evidence del ledger;
- cited Evidence debe ser checked;
- claims sobre records/counts deben estar soportadas por Evidence QUERY correspondiente;
- resultado vacío puede expresarse con confianza alta sólo si existe Evidence checked que demuestra la consulta vacía;
- truncation/limit debe aparecer como limitation cuando afecte a la interpretación;
- respuesta y limitations bounded.

### Observabilidad

Traces técnicos sanitizados para workflow, duración, tool names, counts y error codes; nunca prompts, filtros sensibles completos, tokens ni filas crudas.

## Fuera de scope

- HOW_TO/RAG;
- conversación persistente completa;
- writes/approvals;
- source tools por defecto en QUERY salvo necesidad explícita justificada.

## Tests obligatorios

- QUERY fake con registros y citas válidas;
- aggregate query válida;
- empty result válido/citable;
- invented evidence ref → rechazo;
- model/field/operator manipulado → fail closed;
- `proposed_action` → rechazo;
- budget exhaustion → error controlado;
- prompt injection en valores/records no amplía registry;
- structured QUERY real con Codex si auth disponible;
- suite, Ruff y mypy.

## Acceptance criteria

- existe un product turn QUERY real de sólo lectura;
- Codex sólo puede solicitar las tools QUERY registradas para ese turn;
- resultados/citas se validan server-side;
- EXPLAIN M4 no regresa.

## Después

1. Lista schemas/nombres definitivos de tools QUERY.
2. Muestra un ejemplo de Evidence para records y otro para aggregate/empty result.
3. No avances a M5-05.

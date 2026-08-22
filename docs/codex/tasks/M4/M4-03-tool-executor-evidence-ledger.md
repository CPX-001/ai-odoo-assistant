# M4-03 — ToolExecutor, budgets y evidence ledger

## Contexto

- Requiere M4-02 verde.
- El Source of Truth coloca `ToolExecutor` fuera del modelo: valida policy/schemas/budgets antes de ejecutar adapters.
- Esta task crea la capa host-controlled sin conectar todavía dynamic tools de Codex ni providers reales.

## Objetivo

Implementar una ejecución de tools estrictamente allowlisted y un ledger de Evidence por turn, demostrando que nombres, inputs, outputs, refs y budgets no pueden ser controlados libremente por el modelo.

## Contratos que NO puedes romper

- `ToolSpec` describe una tool; **no autoriza** ejecución;
- `AnswerEnvelope.evidence_refs` sólo contiene UUIDs;
- no framework de plugins universal;
- M4 sólo `READ`/`METADATA`.

## Debes implementar

### Contratos internos mínimos

Define tipos internos claros equivalentes a:

- tool call: call id + tool name + input JSON;
- validated tool result: call id + data bounded + `Evidence[]` añadida;
- executor error con code sanitizado;
- per-turn tool registry construido explícitamente.

No hagas públicos tipos que sólo pertenecen al adapter loop si no hace falta.

### Registry allowlisted

Un registro por turn mapea el `ToolSpec.name`/`executor_id` a un handler concreto ya construido por application/runtime wiring.

- nombres únicos;
- no reflection/import dinámico por string;
- no decorators auto-discovery;
- no `getattr` sobre objetos Odoo como dispatcher;
- cualquier tool no registrada → rechazo.

### Validación

Antes de ejecutar:

- comprobar tool declarada en ese turn;
- `risk` permitido (`read`/`metadata` únicamente);
- validar input contra el contrato Pydantic/schema real del handler;
- máximo de bytes/input nesting razonable;
- deadline restante;
- `max_tool_calls` de `TurnLimits`;
- límites específicos del tool.

Después:

- validar tipo/output;
- cap de bytes;
- normalizar error sin datos sensibles;
- registrar Evidence sólo desde el resultado validado.

### Evidence ledger

Objeto per-turn que:

- indexa `Evidence` por `evidence_id`;
- rechaza UUID duplicado con contenido distinto;
- respeta `max_evidence_items`;
- distingue live/retrieved si hace falta para construir `ContextPack` final;
- permite resolver al final `AnswerEnvelope.evidence_refs`;
- no acepta refs inventadas por el modelo.

El ledger es memoria efímera del turn; persistencia de conversaciones no pertenece a esta task.

### Budgets

Además de `TurnLimits`, define caps server-side de:

- total tool input/output bytes;
- max calls por tool si aporta valor;
- deadline total;
- max Evidence payload bytes enviados al engine.

Los prompts pueden informar estos límites, pero sólo el executor los aplica.

## Fuera de scope

- handlers source/Odoo/log reales;
- dynamicTools/App Server callbacks;
- UI;
- writes/approvals;
- plugin framework.

## Tests obligatorios

- tool desconocida;
- executor_id manipulado;
- risk write/action rechazado;
- input inválido/extra fields;
- output inválido/oversized;
- budget de calls agotado;
- deadline agotado;
- evidence duplicate conflict;
- evidence cap;
- refs finales inexistentes se detectan;
- fake handlers prueban happy path;
- suite, Ruff y mypy.

## Acceptance criteria

- el modelo sólo puede provocar handlers explicitados para el turn;
- schemas y budgets se aplican fuera del modelo;
- Evidence producida tiene una única fuente validada;
- refs inventadas no sobreviven al host;
- no hay provider real conectado todavía.

## Después

1. Lista los budgets elegidos y por qué.
2. Muestra el registry explícito de tests.
3. No avances a M4-04.

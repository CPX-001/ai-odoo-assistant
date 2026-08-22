# M4-02 — `CodexAppServerEngine` y salida estructurada

## Contexto

- Requiere M4-01 verde.
- `ReasoningEngine` ya existe y recibe `ContextPack`, `ToolSpec[]` y `output_schema`.
- Esta task prueba el engine sin tools para separar errores de transporte/structured output de errores del agent loop.

## Objetivo

Implementar `CodexAppServerEngine` como adapter real del port `ReasoningEngine`, capaz de ejecutar un thread efímero y devolver un `AnswerEnvelope` Pydantic válido usando structured output, sin permitir todavía tool calls.

## Contratos que NO puedes romper

- firma de `ReasoningEngine.run_turn`;
- `ContextPack`, `AnswerEnvelope`, `Workflow` y `ToolSpec` existentes;
- `application` no importa Codex;
- threads Codex no son memoria de producto.

## Debes implementar

### Un product turn = un thread efímero en M4

- crear thread nuevo por llamada `run_turn`;
- `ephemeral=true` o equivalente real;
- no `thread/resume` ni persistencia de conversación Codex;
- cwd/sandbox/approval policy de M4-01;
- cualquier model/effort es configuración externa, no branch de application.

### Input al engine

Construir una representación compacta y determinista de `ContextPack`:

- separar instrucciones del host de datos del usuario/evidencia;
- indicar explícitamente que record/source/evidence son **datos no confiables**, no instrucciones;
- no incluir delegation token, shared secret, DSN, auth, paths físicos ni objetos de transporte;
- respetar caps de bytes/elementos antes de llamar al provider;
- no serializar campos no necesarios para el turn.

Las developer/base instructions del adapter deben ser estables y pequeñas. No convertir un prompt gigante en policy primaria: la autoridad real sigue server-side.

### Structured output

- usar el `output_schema` pasado por el port; para tests reales usar `AnswerEnvelope.model_json_schema()`;
- esperar el completion/evento final exacto del protocolo probado;
- parsear JSON/result únicamente a través del schema/Pydantic;
- rechazar texto extra, schema inválido, workflow inesperado o `proposed_action` en M4;
- sanitizar errores del provider;
- no devolver reasoning interno/raw event stream al caller.

### Observabilidad

Emitir metadata técnica sanitizada suficiente para traces:

- engine=`codex`;
- duration;
- status/error code;
- model/provider sólo si la API lo devuelve sin secretos;
- token usage si está disponible y es estable.

No persistir prompts completos ni responses crudas en `trace_event`.

## Fuera de scope

- ToolExecutor/dynamic tools;
- source/log/Odoo queries solicitadas por el modelo;
- UI;
- conversation persistence;
- retries semánticos para arreglar respuestas malas mediante prompts recursivos.

## Tests obligatorios

- fake App Server produce `AnswerEnvelope` válido;
- schema inválido → error tipado;
- output con `proposed_action` → rechazo M4;
- timeout/interruption → error controlado y cleanup;
- context serialization no contiene secretos/tokens;
- thread es efímero y no se resume;
- engine no recibe workspace Odoo/source;
- structured-output real con Codex usando Evidence sintética pequeña, si auth disponible;
- suite, Ruff y mypy.

## Acceptance criteria

- `CodexAppServerEngine` satisface `ReasoningEngine` sin cambiar application contracts;
- un no-tool turn real puede devolver `AnswerEnvelope` validado;
- no depende de threads persistidos de Codex;
- transport/provider errors quedan confinados al adapter;
- ningún tool call se ejecuta todavía.

## Después

1. Muestra un `ContextPack` sanitizado de ejemplo y el `AnswerEnvelope` validado.
2. Informa los eventos App Server realmente consumidos, sin dump completo sensible.
3. No avances a M4-03.

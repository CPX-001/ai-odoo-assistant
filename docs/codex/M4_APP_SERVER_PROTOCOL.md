# M4 Codex App Server protocol baseline

Fecha de verificación: 2026-08-22.

## Runtime inspeccionado

- Runtime inspeccionado en Codex para Windows: `codex-cli
  0.149.0-alpha.4.1`.
- Smoke real reproducible en Linux: `@openai/codex 0.149.0`, instalado
  temporalmente fuera del repositorio; el probe devolvió
  `compatible/app-server-jsonl-v2/0.149.0`.
- Transporte elegido para el producto Linux: `codex app-server --stdio
  --strict-config --config mcp_servers={}`. El último override impide que MCPs
  del perfil personal del usuario entren en un product turn.
- El comando `codex app-server generate-json-schema --experimental` confirmó
  el protocolo JSONL actual y sus schemas v2.
- Secuencia mínima probada: request `initialize`, response con el mismo `id` y
  notification `initialized`.
- La versión inspeccionada también declara `thread/start`, `turn/start`,
  `outputSchema`, threads `ephemeral`, `approvalPolicy`, `sandbox`,
  `runtimeWorkspaceRoots` y `dynamicTools`.

La documentación pública oficial de Codex y el runtime instalado no exponen un
SDK Python que controle este lifecycle manteniendo App Server como boundary.
Por ello M4-01 usa un cliente JSONL mínimo, sin vendorización del schema y sin
replicar el protocolo completo. Los nombres y shapes concretos quedan en
`odoo_ai.adapters.codex_runtime`; `application`, contracts y Odoo no dependen
de ellos.

## Configuración externa

- `ODOO_AI_CODEX_EXECUTABLE`: path absoluto al runtime seleccionado; no existe
  un path DEV como default de producto.
- `ODOO_AI_CODEX_HOME`: override explícito opcional. Si se omite, Codex resuelve
  su auth bajo el usuario efectivo del Assistant Service.
- `ODOO_AI_CODEX_MODEL`: modelo opcional; ningún nombre de modelo es contrato.
- `ODOO_AI_CODEX_ISOLATED_CWD`: cwd aislado opcional. Si se omite se crea uno
  temporal por proceso.
- `ODOO_AI_CODEX_STARTUP_TIMEOUT_SECONDS` y
  `ODOO_AI_CODEX_TURN_TIMEOUT_SECONDS`: límites externos validados.
- `ODOO_AI_CODEX_EXPERIMENTAL_API`: opt-in booleano explícito. La versión
  0.149.0 lo requiere para negociar `dynamicTools`, `environments` y
  `runtimeWorkspaceRoots`; M4-02 falla cerrado si no está activo.

El child recibe un allowlist mínimo de variables de proceso, no el DSN,
shared secret, delegation secret ni configuración Odoo. El adapter nunca copia
ni parsea `auth.json`.

## Lifecycle y aislamiento preparados

```text
spawn argv fijo, shell=False
    -> initialize (id correlacionado)
    -> validate bounded response
    -> initialized
    -> ephemeral thread: approval=never, sandbox=read-only,
       runtimeWorkspaceRoots=[], environments=[], dynamicTools allowlisted
    -> close stdin
    -> graceful wait
    -> TERM/KILL bounded fallback
```

El probe sólo declara compatibilidad de protocolo. Auth y modelo permanecen
`unknown` hasta que una task posterior obtenga evidencia real de un turn.

El smoke se puede repetir pasando el path absoluto del binario a
`ODOO_AI_CODEX_EXECUTABLE`, activando `ODOO_AI_RUN_CODEX_RUNTIME_SMOKE=1` y
ejecutando `tests/integration/test_codex_runtime_smoke.py`. No necesita login ni
consume un product turn.

## M4-02: turn estructurado sin tools

`CodexAppServerEngine` crea un proceso y un thread nuevo por cada llamada al
port. Consume únicamente esta secuencia relevante:

```text
initialize response
  -> thread/start response (thread.id + ephemeral=true)
  -> turn/start response (turn.id)
  -> item/completed notifications bounded (validación de tipo)
  -> turn/completed del mismo thread/turn
  -> último agentMessage.text
  -> JSON decode + AnswerEnvelope.model_validate
```

El adapter acepta sólo notifications inspeccionadas y acotadas, incluidas
`configWarning`, `warning`, `thread/started`, token usage, rate limits y estados
de runtime/MCP; las descarta sin exponer detalles. Cualquier evento desconocido
falla cerrado. Un item de tool, un server request, IDs distintos, estado failed,
texto extra, evidencia desconocida, workflow distinto o `proposed_action`
producen un error tipado sanitizado.

Pydantic genera `AnswerEnvelope.model_json_schema()` con un `JsonValue` abierto
y campos con default. El structured output estricto real de Codex 0.149.0 no
acepta ese shape literalmente. El adapter usa esa schema como fuente, verifica
sus seis propiedades y crea una copia provider-compatible: todos los campos son
required, `proposed_action` queda restringido a `null` en M4 y se eliminan las
defs abiertas que ya no son alcanzables. La respuesta sigue validándose con el
modelo Pydantic original; la normalización no relaja el contrato.

Ejemplo del payload compacto enviado como único input de texto:

```json
{
  "host_contract": {
    "data_trust": "untrusted",
    "max_evidence_refs": 1,
    "tools_available": false
  },
  "untrusted_data": {
    "conversation": {
      "last_user_intent": null,
      "mentioned_records": [],
      "short_summary": ""
    },
    "evidence": [{
      "evidence_id": "12345678-1234-5678-1234-567812345678",
      "kind": "record",
      "payload": {"state": "sale"},
      "status": "checked",
      "summary": "The synthetic quotation is in the sale state.",
      "title": "Synthetic quotation"
    }],
    "instance_capabilities": [],
    "screen": {"model": "sale.order", "res_id": 56},
    "user_request": "Explain the state using only the supplied evidence.",
    "workflow_hint": "EXPLAIN"
  }
}
```

Campos opcionales nulos y metadata no sensible pueden aparecer en la forma
canónica completa. No aparecen user identity, `instance_id`, context dict del
browser, tokens, secrets, DSN ni paths físicos.

Ejemplo de respuesta aceptada por el host:

```json
{
  "answer_markdown": "The checked record is in the sale state.",
  "workflow": "EXPLAIN",
  "confidence": "high",
  "evidence_refs": ["12345678-1234-5678-1234-567812345678"],
  "limitations": [],
  "proposed_action": null
}
```

El smoke opt-in `tests/integration/test_codex_engine_smoke.py` pasó contra
`codex-cli 0.149.0` y una sesión existente del usuario del host, con evidencia
sintética y sin dynamic tools. La auth siguió gestionada por Codex; el test no
copió ni leyó el contenido del token. El model/provider sólo se conservan como
metadata técnica acotada cuando la response de `thread/start` los declara.

## M4-04: server requests de dynamic tools

Con `experimentalApi=true`, `thread/start.dynamicTools` registra funciones con
`type`, `name`, `description` e `inputSchema`. Codex 0.149 aplica al nombre la
regex Responses-compatible `^[a-zA-Z0-9_-]+$`; por ello el detalle de transporte
usa aliases sin puntos y el contrato lógico `source.*` no cambia fuera del
adapter.

Durante el turn, App Server envía un JSON-RPC server request
`item/tool/call`. El cliente lo conserva en la misma cola bounded de eventos y
el engine correlaciona request id, thread id, turn id y call id antes de delegar
al `ToolExecutor`. La response exacta probada es:

```json
{
  "id": 100,
  "result": {
    "success": true,
    "contentItems": [
      {"type": "inputText", "text": "{...JSON canónico bounded...}"}
    ]
  }
}
```

Requests desconocidos, IDs duplicados y presupuestos agotados fallan cerrado.
Un input que no satisface el schema y errores source recuperables como un
fingerprint stale se devuelven con `success=false`, sin ejecutar el backend ni
crear Evidence checked, para permitir un reintento o una limitación acotada. El
presupuesto agregado de tools es 120 s y cada handler mantiene un timeout de 5
s. El smoke dinámico real reproducible está en
`tests/integration/test_codex_dynamic_tools_smoke.py`.

## M4-09/M4-10: vertical real y gate

El runner desechable ejecutó Chromium, Odoo 18, Assistant Service y Codex
0.149.0 autenticado. El turno usó las tres source tools reales, citó el pedido
y `odoo_ai_m3_sale_project/models/sale_order.py`, y comprobó la creación exacta
de una `project.task`. También verificó source stale, runtime ausente,
`FULLY_READY`/`DEGRADED`, aislamiento de DB y limpieza de procesos. Véanse
[`M4_E2E_REPORT.md`](M4_E2E_REPORT.md) y
[`M4_GATE_REPORT.md`](M4_GATE_REPORT.md).

El baseline coincide con la documentación oficial del
[Codex App Server](https://learn.chatgpt.com/docs/app-server); los detalles
experimentales siguen confinados al adapter.

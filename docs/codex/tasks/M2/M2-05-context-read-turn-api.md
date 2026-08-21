# M2-05 — Turn API de context-read determinista

## Contexto

- Requiere M2-04 verde.
- M2 debe demostrar el pipeline contextual completo antes de integrar un LLM.
- M1 ya tiene FastAPI, Assistant DB, instance/capability status y traces sanitizados.

## Objetivo

Añadir al Assistant Service un ingress autenticado para un turn contextual de sólo lectura que valide el request, construya contexto mínimo y use `OdooGateway` para releer determinísticamente el registro de `ScreenContext`, devolviendo una respuesta estructurada sin ReasoningEngine.

## Contratos que NO puedes romper

- browser nunca llama al Assistant Service;
- ingress Odoo → service usa machine-auth de M1;
- delegación no llega a prompts/traces/responses de usuario;
- `ScreenContext` se trata como hint y se verifica mediante relectura;
- `OdooGateway` es la única vía de datos vivos Odoo para el service.

## Debes reutilizar

- FastAPI `create_app()`/auth dependency existente;
- schemas M2-01;
- `OdooGateway` adapter M2-04;
- `ContextPack`, `RecordRef`, `RecordSnapshot`, `Evidence`, `InstanceProfileSummary` cuando aporten valor real;
- `trace_event` sólo para metadata técnica sanitizada.

## Debes implementar

### 1. Ingress estrecho

Crear una ruta M2 claramente nombrada. Si el Source of Truth ya fija el endpoint final de turns, úsalo; si no, preferir un nombre que no finja agent-loop completo, por ejemplo `/v1/turns/context-read`.

Requisitos:

- `POST` autenticado con shared secret;
- body Pydantic estricto;
- tamaño máximo de mensaje/request;
- `turn_id`, screen, user y token según M2-01;
- rechazo de screen sin `model`/`res_id` para este vertical slice;
- screen demasiado antiguo/IDs absurdos → rechazo controlado.

### 2. Context assembly mínimo

Construir sólo lo necesario para M2:

- request del usuario;
- `ScreenContext` validado;
- `UserExecutionContext` recibido desde Odoo server autenticado;
- instance summary disponible;
- límites server-side;
- estado de conversación vacío/efímero si no existe persistencia todavía.

No crear RAG, source/log evidence ni memoria persistente sólo para rellenar `ContextPack`.

### 3. Relectura determinista

Para `screen.model` + `screen.res_id`:

1. obtener metadata bounded;
2. elegir un conjunto **determinista y pequeño** de fields útiles para demostrar la relectura (`display_name` y, si existen/son accesibles, un puñado como `name`, `state`, `company_id`); no inferir fields desde el texto mediante heurísticas complejas;
3. llamar `read_records` con ese único `RecordRef`;
4. convertir el resultado a evidencia/snapshot estructurado.

La respuesta M2 puede ser determinista, por ejemplo indicar que el registro fue releído bajo permisos del usuario y mostrar `display_name`/estado. No pretender responder semánticamente preguntas libres: eso pertenece a M4.

### 4. Observabilidad segura

Registrar sólo ids técnicos, duración, operation names, count/status y fingerprints seguros. No persistir en `trace_event`:

- mensaje crudo;
- token;
- shared secret;
- headers;
- payload completo del registro.

## Fuera de scope

- ReasoningEngine/Codex;
- ToolExecutor genérico;
- loops de tools;
- conversation memory completa;
- search/domain queries;
- source/logs/RAG;
- writes/actions.

## Restricciones

- no acceso SQL Odoo;
- no llamada a endpoints distintos de OdooGateway;
- no tool selection por LLM;
- no campos ilimitados;
- no guardar token/request raw en traces.

## Tests obligatorios

- request válido con fake gateway → response contextual válida;
- missing/invalid machine auth → 401/403;
- screen sin model/res_id → 4xx estructurado;
- gateway AccessDenied → error sanitizado sin filtrar existencia;
- delegation/token nunca aparece en response/trace;
- field selection es bounded y determinista;
- instance/profile ausente se representa como unknown/degraded, no se inventa;
- integración con adapter HTTP M2-04;
- suite, Ruff, mypy.

## Acceptance criteria

- Odoo server puede enviar un turn contextual al service;
- el service relee el registro sólo por `OdooGateway`;
- la respuesta demuestra datos frescos de ORM, no datos de `ScreenContext`;
- no hay LLM ni agent loop;
- auth/limits/traces son seguros;
- tests verdes.

## Antes de editar

1. Inspecciona API/status/tracing actuales.
2. Resume el schema exacto de request/response propuesto.
3. Señala si introduces un endpoint temporal o el endpoint definitivo del Source of Truth.

## Después

1. Ejecuta tests.
2. Muestra un ejemplo de request/response sanitizados sin secretos.
3. Informa qué fields deterministas se releen y por qué.
4. No avances a M2-06.

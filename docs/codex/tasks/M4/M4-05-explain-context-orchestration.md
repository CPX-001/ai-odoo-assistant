# M4-05 — Orquestación `EXPLAIN` con record + source evidence

## Contexto

- Requiere M4-04 verde.
- M2 ya valida `ScreenContext`, deriva identidad/delegación y relee el current record por ORM.
- M3 aporta source evidence; M4-04 la hace accesible al engine mediante tools.
- Esta task une esas piezas en `application`; todavía no toca el browser.

## Objetivo

Crear un workflow `EXPLAIN` que prelea el registro actual bajo el usuario real, construya `ContextPack`, ejecute `ReasoningEngine` con source tools y produzca una respuesta final cuyas citas resuelvan únicamente a Evidence real del turn.

## Debes reutilizar

- validaciones/request preparation de M2 sin copiar dos implementaciones divergentes;
- `OdooGatewayFactory`/delegation boundary;
- `_record_evidence` o una extracción reusable equivalente;
- `ContextPack`, `ConversationState`, `TurnLimits`, `Workflow.EXPLAIN`;
- ToolExecutor/evidence ledger;
- Codex engine M4-02/M4-04.

## Debes implementar

### Contrato de turn

Crear un request/response estrecho para M4, sin intentar anticipar M5 completo.

Request equivalente a M2:
- `turn_id`;
- message;
- `ScreenContext`;
- `UserExecutionContext` derivado por Odoo;
- delegation token server-only;
- gateway/instance reference estrictamente necesaria.

Response debe contener como mínimo:
- turn id;
- `AnswerEnvelope` o fields explícitos equivalentes ya validados;
- citas renderizables y sanitizadas;
- completed_at/status técnico mínimo.

No devolver delegation token ni raw tool transcript.

### Pre-read determinista

Antes de Codex:

1. validar screen/user/edad como M2;
2. construir gateway por turn;
3. releer exactamente el current record mediante ORM bajo la delegación;
4. convertirlo a `Evidence(kind=record, status=checked)`;
5. añadirlo como `live_evidence`/ledger.

No pedir a Codex que averigüe el current record desde cero.

### ContextPack

- `workflow_hint=EXPLAIN`;
- request del usuario;
- screen/user efectivos;
- instance summary;
- record evidence ya disponible;
- conversation state mínimo, sin inventar historial;
- budgets pequeños y server-side.

### Reasoning + source

Permitir al engine sólo las source tools M4-04. Para la pregunta objetivo debe poder descubrir extensiones de `sale.order`, localizar `action_confirm` y leer el excerpt causal.

### Validación final

Después de `ReasoningEngine`:

- workflow debe ser `EXPLAIN`;
- `proposed_action` debe ser `None`;
- todos los `evidence_refs` deben existir en el ledger;
- refs duplicadas se normalizan/rechazan según contrato;
- Evidence stale/failed no cuenta como soporte checked;
- `high` requiere soporte checked suficiente para las afirmaciones del vertical slice; como mínimo record + source para el E2E objetivo;
- si source no está disponible/stale, devolver limitación/confidence degradada o error controlado, nunca inventar causalidad.

No intentes verificar semánticamente cada frase con otro LLM. Valida estructura, provenance y reglas deterministas.

### Citas de presentación

Derivar desde Evidence tipos seguros como:

- record: model/id/display_name/captured_at;
- source: module/logical_path/start-end lines/fingerprint/provenance.

No enviar payload completo de Evidence al browser por defecto.

### Tracing

Extiende la traza actual con eventos sanitizados:

- context prepared;
- record evidence added;
- reasoning started/completed;
- tool requested/completed (sin raw args sensibles);
- evidence added;
- answer validated;
- turn completed/error.

No persistir prompt, source excerpt completo ni model response completa en `trace_event`.

## Fuera de scope

- UI/Odoo bridge;
- logs agent tool;
- multi-turn memory;
- QUERY/HOW_TO;
- writes/approvals.

## Tests obligatorios

- fake engine sin tool devuelve explicación soportada por record evidence cuando procede;
- fake engine usa source tools y devuelve refs válidas;
- ref inventada → rechazo;
- source stale/unavailable → no confidence high engañosa;
- proposed_action → rechazo;
- record ACL failure sigue siendo access_denied;
- turn budgets respetados;
- trace no contiene delegation token/prompt/source raw;
- suite, Ruff y mypy.

## Acceptance criteria

- existe un `EXPLAIN` application workflow desacoplado de Codex concreto;
- current record siempre se relee antes de razonar;
- source evidence sólo entra por ToolExecutor;
- la respuesta final sólo cita evidencia real del turn;
- no se ha tocado todavía frontend.

## Después

1. Muestra el flujo de dependencias final.
2. Lista reglas deterministas de validación de `AnswerEnvelope`.
3. No avances a M4-06.

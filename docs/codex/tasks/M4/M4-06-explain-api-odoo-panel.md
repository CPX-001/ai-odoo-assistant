# M4-06 — API `EXPLAIN`, bridge Odoo y panel con citas

## Contexto

- Requiere M4-05 verde.
- M2 ya tiene browser → Odoo → Assistant Service, `prepare_context_turn`, `AssistantServiceClient` y panel OWL.
- No crear una segunda arquitectura de UI ni hacer que el browser hable directamente con Codex/Assistant.

## Objetivo

Hacer accesible el workflow `EXPLAIN` desde el panel existente y renderizar una respuesta con citas de record/source sanitizadas, manteniendo identidad, delegación, machine auth y endpoints internos exclusivamente server-side.

## Debes reutilizar

- `odoo.ai.assistant.bridge`;
- `prepare_context_turn` y delegación M2;
- `AssistantServiceClient`;
- panel/service de frontend M2;
- response/citation contract M4-05.

## Assistant Service API

Añadir un endpoint estrecho, por ejemplo `POST /v1/turns/explain`, con:

- machine auth M1;
- request Pydantic M4;
- bounded body middleware;
- errores sanitizados;
- `response_model` explícito;
- dependency injection suficiente para tests.

No reutilices `/v1/admin/*` para turns de usuario y no expongas dynamic tool transcript.

Mantén `/v1/turns/context-read` de M2 mientras siga siendo útil para regresiones; no lo borres sólo para reducir duplicación. Extrae validaciones/helpers comunes cuando haya duplicación real.

## Odoo server bridge

Añadir una operación server-side de explicación que:

1. reciba sólo message + ScreenContext del browser;
2. compruebe usuario interno;
3. derive identidad efectiva y delegación con el mismo mecanismo M2;
4. llame al Assistant Service desde Odoo server;
5. valide estrictamente el response shape;
6. reduzca el resultado a campos renderizables seguros.

El browser nunca recibe:

- delegation token;
- shared secret;
- `ODOO_AI_ODOO_BASE_URL`/Assistant internal URL;
- uid/company authority como dato confiable;
- raw Evidence payload;
- raw App Server events/errors.

## Respuesta browser

Shape pequeño equivalente a:

- `ok`;
- turn id;
- answer markdown/text;
- confidence;
- limitations;
- citations[] discriminadas (`record`/`source`);
- error code controlado cuando falla.

Validar tamaños, tipos y que las citations pertenecen al mismo current record/source refs ya validados por el service.

## Panel

Evolucionar el panel M2 sin rediseño grande:

- textarea/input de pregunta actual;
- loading/disabled contra doble submit;
- respuesta visible;
- confidence/limitations discretos;
- citas clicables/expandibles sólo si no requieren exponer paths físicos;
- cita record: display name/model/id;
- cita source: module/logical path/lines/fingerprint corto o completo según UX;
- errores `access_denied`, engine unavailable, evidence unavailable, timeout.

### Markdown/XSS

`AnswerEnvelope.answer_markdown` es texto no confiable generado por modelo. No usar `t-raw`, `innerHTML` ni parser permissivo sin sanitización. Para M4 es válido renderizarlo como texto/pre-line o usar un renderer Odoo ya sanitizado y probado. Añade tests con `<script>`, links `javascript:` y HTML arbitrario.

## Fuera de scope

- streaming token a token;
- persistir historial de chat;
- editar source/log settings desde panel;
- feedback/rating;
- QUERY/HOW_TO;
- writes/approvals.

## Tests obligatorios

- API explain happy path con fake engine/tools;
- request oversized/invalid → controlado;
- Odoo bridge ignora identidad browser y deriva la real;
- browser payload no contiene tokens/secrets/internal URL/raw Evidence;
- response con citation/ref manipulada → rechazo;
- doble submit no crea dos turns simultáneos desde UI;
- markdown/HTML adversarial no ejecuta script;
- errores de Codex/timeouts se mapean a UI segura;
- assets/tests OWL existentes siguen verdes;
- suite, Ruff, mypy y tests Odoo aplicables.

## Acceptance criteria

- un usuario interno puede enviar una pregunta contextual al workflow M4 desde el panel;
- toda autoridad sigue server-side;
- la UI muestra respuesta + citas seguras;
- browser no conoce transport/auth internos;
- M2 contextual-read sigue funcionando como regresión.

## Después

1. Muestra el response exacto browser-facing sin datos sensibles.
2. Adjunta evidencia de tests XSS/doble submit.
3. No avances a M4-07.

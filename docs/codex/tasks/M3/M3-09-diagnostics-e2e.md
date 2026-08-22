# M3-09 — Diagnostics + vertical slice real de source/logs

## Contexto

- Requiere M3-08 verde.
- El resultado observable de M3 debe poder comprobarse desde Diagnostics.
- M4 usará este subsistema para explicar “¿por qué confirmar crea tarea?”, pero M3 no introduce Codex.
- El Source of Truth pide fixture Odoo 18 CE con `sale + project` y un addon que sobrescriba `sale.order.action_confirm`.

## Objetivo

Integrar scanner + source queries + LogProvider en Diagnostics y demostrarlos E2E sobre Odoo 18 real con fixtures reproducibles.

## Contratos que NO puedes romper

- Diagnostics es superficie admin Odoo → Assistant Service;
- browser no habla directamente con Assistant Service;
- endpoints admin autenticados con machine/shared-secret;
- no exponer path arbitrario ni token al browser;
- M2 context-read no se reescribe.

## Debes reutilizar

- `odoo.ai.assistant.diagnostics`;
- `AssistantServiceClient`;
- `/v1/admin/status`;
- machine-auth/shared secret;
- fixture/harness Odoo 18 de M2;
- scan/source/log application services M3.

## Debes implementar

### 1. Fixture Odoo 18

Crear/usar un addon fixture que:
- depende de `sale` + `project`;
- sobrescribe `sale.order.action_confirm`;
- bajo una condición explícita y visible crea/actualiza `project.task`;
- contiene suficiente source para que scanner encuentre método, condición y creación de task;
- no se hardcodea en código de producto.

Reutilizar usuarios/permisos M2 cuando sea posible.

### 2. Fixture de logs

Proporcionar un traceback controlado reproducible:
- file log real/fixture para gate;
- Journal provider se prueba por contract/integration cuando el host lo permita;
- términos y timestamps conocidos.

No persistir el log completo en Assistant DB.

### 3. Endpoints admin bounded

Añadir sólo los endpoints necesarios para Diagnostics:
- lanzar/reanalizar scan;
- obtener scan status/fingerprint;
- test source search (`action_confirm`);
- test logs/search/traceback.

No crear filesystem/log explorer genérico.

### 4. Odoo Diagnostics

Extender la vista/modelo actual para mostrar:
- source state;
- source last scan/fingerprint;
- log provider/state;
- botón `Reanalizar source`;
- botón/test source;
- botón/test logs;
- resultado sanitizado y bounded.

No mostrar shared secret, tokens ni config sensible completa.

### 5. Readiness

Tras M3:
- source = operational en fixture;
- logs = operational en fixture;
- overall sigue `DEGRADED` porque `reasoning_engine` permanece pendiente de M4.

### 6. E2E

Demostrar desde Odoo Diagnostics:
1. scan;
2. búsqueda `sale.order.action_confirm`;
3. módulo/path lógico/líneas correctas;
4. excerpt correcto;
5. búsqueda de log por ventana/terms;
6. traceback recuperable/fingerprint;
7. cambiar source fixture + rescan;
8. old fingerprint queda stale y new fingerprint activo.

## Fuera de scope

- preguntar al LLM;
- dynamicTools;
- AnswerEnvelope real de M4;
- RAG docs;
- QUERY;
- writes/actions.

## Restricciones

- no repo completo en response;
- no log completo en response;
- no source/log path libre desde UI;
- no user identity necesaria para admin source/log diagnostics;
- sólo admins pueden usar estas acciones.

## Tests obligatorios

- addon install/update Odoo 18;
- scanner E2E;
- exact lines;
- stale hash/rescan;
- FileLogProvider E2E;
- Diagnostics access admin/non-admin;
- browser boundary;
- secret hygiene;
- M1 regression;
- M2 regression;
- lint/type-check.

## Acceptance criteria

- desde Diagnostics se encuentra `action_confirm` con módulo/fichero/líneas;
- desde Diagnostics se recupera el traceback fixture bounded;
- source/log capabilities están operativas;
- overall readiness no se declara FULLY_READY prematuramente;
- M1/M2 siguen PASS.

## Antes de editar

1. Describe fixture exacta.
2. Lista endpoints admin mínimos.
3. Señala qué datos llegan realmente al browser.

## Después

1. Adjunta evidencia de E2E.
2. Informa líneas/fingerprint del símbolo y traceback.
3. Ejecuta suites completas.
4. No avances a M3-10.

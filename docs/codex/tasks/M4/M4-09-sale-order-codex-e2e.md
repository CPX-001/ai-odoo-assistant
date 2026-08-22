# M4-09 — E2E real: «¿por qué confirmar este pedido crea una tarea?»

## Contexto

- Requiere M4-08 verde.
- M3 ya incluye el fixture `odoo_ai_m3_sale_project`, cuyo `sale.order.action_confirm` permite probar causalidad de source con líneas/fingerprint exactos.
- Esta task debe usar Odoo, Assistant Service **y Codex reales**. Los fakes no cuentan para el acceptance principal.

## Objetivo

Demostrar desde el panel Odoo que un usuario puede preguntar por qué confirmar el pedido crea una tarea y recibir una explicación útil generada por Codex que cite el `sale.order` releído y el source exacto responsable del efecto.

## Preparación del fixture

En entorno disposable/reproducible:

- Odoo 18 Community real;
- addon `odoo_ai_assistant` actualizado;
- fixture `odoo_ai_m3_sale_project` instalado;
- PostgreSQL/Assistant DB migrados;
- source scan M3 vigente;
- Codex runtime compatible y autenticado bajo el usuario del Assistant;
- usuario interno de test con permisos reales suficientes sobre el `sale.order`, sin convertirlo en superuser sólo para que pase.

Crear un pedido conocido y confirmar/observar el efecto del fixture cuando sea necesario para comprobar la causalidad real. No falsear la respuesta esperada sólo con texto del prompt.

## Flujo E2E

Con Playwright/browser real cuando sea viable:

1. login como usuario interno;
2. abrir el `sale.order` fixture;
3. abrir panel del Assistant;
4. preguntar en castellano algo equivalente a: `¿Por qué al confirmar este pedido se crea una tarea?`;
5. Odoo deriva identidad/delegación;
6. Assistant relee current record;
7. Codex recibe ContextPack;
8. Codex usa source tools allowlisted;
9. `read_excerpt` produce Evidence checked;
10. respuesta vuelve a Odoo y panel la muestra con citas.

## Assertions semánticas mínimas

No fijar la prosa exacta del LLM. Validar estructura y hechos esenciales:

- la respuesta identifica que una extensión/custom module de `sale.order.action_confirm` introduce el efecto;
- relaciona la confirmación con la creación de `project.task`/tarea según el código fixture;
- no atribuye el efecto únicamente al core si el fixture demuestra lo contrario;
- si menciona una condición/campo concreto, debe estar soportado por el excerpt/record evidence disponible.

Si el output no satisface esos hechos, el E2E falla; no relajar la assertion a «devolvió texto».

## Assertions de evidencia

La respuesta final debe incluir refs/citas resolubles a:

### Record

- model `sale.order`;
- id actual;
- display name correcto;
- captured_at de la relectura ORM.

### Source

- module real (`odoo_ai_m3_sale_project` en el fixture actual);
- logical path real;
- símbolo/método `action_confirm`;
- rango de líneas actual del scan, sin hardcodearlo en product code;
- fingerprint vigente;
- Evidence status checked.

Verificar que las refs de `AnswerEnvelope` corresponden a las Evidence realmente usadas por el turn.

## Assertions de boundary

- browser → Assistant direct requests = 0;
- browser no ve delegation/shared secret/internal endpoint;
- Codex no recibe physical source root;
- source excerpt se obtuvo mediante tool call, no filesystem built-in;
- no shell/Odoo SQL/writes del agent loop;
- traces no contienen prompt/source completo ni secretos.

## Casos negativos mínimos

Ejecutar al menos:

- usuario sin acceso al pedido → access denied antes de una explicación soportada;
- source capability ausente/stale → no respuesta high-confidence inventada;
- Codex no disponible → error UI controlado/readiness degraded;
- tool budget insuficiente → limitation/error bounded, no loop infinito.

## Reproducibilidad

Añadir un runner/smoke M4 separado de los unit tests pesados, documentando variables/env necesarias sin credenciales. El runner debe limpiar DBs/processes/fixtures temporales que cree.

No subir auth de Codex ni tokens al repo.

## Acceptance criteria

- el flujo real completo funciona desde UI;
- Codex ejecuta al menos un source tool real;
- la explicación contiene la causalidad esencial del fixture;
- record + source exactos aparecen como citas válidas;
- permisos/seguridad M2 siguen siendo autoritativos;
- los negativos fallan de forma controlada;
- fakes no sustituyen esta evidencia.

## Después

1. Registra pregunta, hechos esperados, respuesta resumida y citas (sin secretos).
2. Registra tool sequence y counts, no raw hidden reasoning.
3. Deja comandos reproducibles para M4-10.
4. No avances a M4-10 automáticamente.

# M4 — Codex vertical slice

Estado: M4-01 y M4-02 implementadas y verificadas; M4-03 es la siguiente task.

M4 empieza únicamente después de **M3 GATE: PASS**. Su objetivo es conectar el `ReasoningEngine` real con Codex App Server y cerrar un primer turno agéntico de sólo lectura: desde un `sale.order` abierto, responder por qué al confirmarlo se crea una tarea, apoyándose en el registro releído bajo el usuario efectivo y en source indexado/fingerprint-checked.

Fuente de verdad: `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`, `docs/ARCHITECTURE.md`, `AGENTS.md`, `service/AGENTS.md`, `addons/AGENTS.md`, `tests/AGENTS.md` y el estado real dejado por M0-M3. El protocolo concreto de Codex debe contrastarse además con la versión real/SDK oficial disponible al implementar; los detalles cambiantes del App Server pertenecen al adapter, no a `application`.

Resultado observable del milestone:

```text
usuario abre sale.order y pregunta por un efecto
    ↓
Odoo deriva identidad + delegación server-side
    ↓
Assistant relee el registro por ORM como ese usuario
    ↓
ContextPack + Evidence(record)
    ↓
CodexAppServerEngine
    ↓
ToolExecutor sólo ofrece source tools allowlisted
    ↓
source.find_* / source.read_excerpt
    ↓
Evidence(source) fingerprint-checked
    ↓
AnswerEnvelope con evidence_refs válidos
    ↓
Odoo sanitiza respuesta + citas
    ↓
panel muestra explicación y record/source exactos
```

M4 no convierte Codex en una autoridad. Cada product turn usa un contexto y tools explícitos; el Assistant Service valida todos los tool calls, budgets y evidencias. Los threads de Codex son efímeros en este milestone y **no son memoria de producto**.

## Orden de ejecución

1. [`M4-01-codex-app-server-runtime.md`](M4-01-codex-app-server-runtime.md) — runtime/protocolo App Server, lifecycle seguro y probe real.
2. [`M4-02-codex-reasoning-engine-structured-output.md`](M4-02-codex-reasoning-engine-structured-output.md) — adapter `ReasoningEngine` con `ContextPack` y `AnswerEnvelope` estructurado, todavía sin tools.
3. [`M4-03-tool-executor-evidence-ledger.md`](M4-03-tool-executor-evidence-ledger.md) — ejecución host-controlled, budgets y ledger de evidencia por turn.
4. [`M4-04-source-tools-dynamic-bridge.md`](M4-04-source-tools-dynamic-bridge.md) — source tools allowlisted y bridge de dynamic tools de Codex.
5. [`M4-05-explain-context-orchestration.md`](M4-05-explain-context-orchestration.md) — workflow `EXPLAIN`: current-record evidence + reasoning + validación de citas.
6. [`M4-06-explain-api-odoo-panel.md`](M4-06-explain-api-odoo-panel.md) — endpoint, bridge server-side y panel con respuesta/citas.
7. [`M4-07-reasoning-readiness-diagnostics.md`](M4-07-reasoning-readiness-diagnostics.md) — capability/readiness de Codex y `FULLY_READY` cuando corresponde.
8. [`M4-08-security-injection-budget-hardening.md`](M4-08-security-injection-budget-hardening.md) — prompt injection, eventos prohibidos, límites y fallos del App Server.
9. [`M4-09-sale-order-codex-e2e.md`](M4-09-sale-order-codex-e2e.md) — E2E real browser → Odoo → Assistant → Codex → source → respuesta citada.
10. [`M4-10-gate.md`](M4-10-gate.md) — gate integral y cierre de M4.

Ejecutar una sola task cada vez. Cada packet debe partir del estado real dejado por el anterior, ejecutar sus verificaciones y detenerse. No avanzar automáticamente.

## Invariantes de M4

- Codex implementa `ReasoningEngine`; no invade `application`, Odoo ni providers.
- El modelo no recibe shared secret, delegation token, credenciales Odoo, DSN, auth de Codex ni paths físicos de deployment.
- Codex no obtiene filesystem/shell del host como shortcut para consultar Odoo/source/logs.
- El cwd del thread es aislado y no convierte los roots Odoo/source en workspace del modelo.
- Un thread efímero por product turn; no depender de historial/thread state de Codex para memoria del producto.
- `ToolExecutor`, fuera del modelo, valida tool name, input, scope, budgets, deadline y output antes de devolverlo a Codex.
- M4 sólo expone tools `read`/`metadata` estrictamente necesarias. No `execute_kw`, `execute_method`, shell, SQL, Python arbitrario ni writes.
- El registro contextual se relee mediante el `OdooGateway`/delegación de M2 bajo el usuario real antes de razonar.
- Source se obtiene sólo mediante refs/index M3; `read_excerpt` sigue revalidando root + fingerprint y nunca acepta path libre.
- Evidence recuperada se trata como datos no confiables; instrucciones dentro de records/source no cambian policy ni tool authority.
- `AnswerEnvelope.evidence_refs` debe resolver únicamente a Evidence realmente producida en ese turn.
- Una respuesta no puede afirmar `high` con citas inexistentes/stale; el host valida refs y degrada/rechaza de forma explícita.
- El browser recibe una representación sanitizada de respuesta/citas, nunca Evidence interna completa si no es necesaria.
- Los detalles/versiones del protocolo Codex quedan confinados al adapter. Si cambia App Server, no se modifica `application`.
- M4 no implementa QUERY server-side genérico, HOW_TO/RAG documental, conversación persistente compleja, writes, approvals ni business actions.

## Gate de M4

M4 sólo se considera terminado cuando:

- Codex App Server arranca/handshakea bajo el usuario del Assistant con configuración soportada y sin shell wrapper;
- `CodexAppServerEngine` satisface el port `ReasoningEngine` y devuelve `AnswerEnvelope` validado;
- tool calls se ejecutan sólo mediante `ToolExecutor` allowlisted y respetan budgets server-side;
- el modelo puede localizar `sale.order.action_confirm`, solicitar excerpt y recibir Evidence source vigente;
- el current `sale.order` se relee bajo el usuario efectivo de Odoo y forma parte de las citas finales;
- manipular tool args, evidence refs o output estructurado no amplía autoridad;
- source/record con texto adversarial no puede habilitar herramientas ni revelar secretos;
- la UI muestra explicación + citas de record/source sin acceso directo del browser al Assistant Service;
- el E2E real con Codex explica correctamente el fixture que crea `project.task` desde `action_confirm` y cita módulo/fichero/líneas/fingerprint reales;
- M1/M2/M3 no regresan; tests, Ruff y mypy siguen verdes;
- con DB/migrations/source/logs/reasoning operativos, readiness puede llegar a `FULLY_READY` según el Source of Truth.

Un fake App Server es válido para unit/integration tests, pero **no** para declarar M4 GATE PASS. Si no existe una sesión Codex autenticada/usable en el host de gate, el resultado es CONDITIONAL/FAIL y se indica la prueba real pendiente.

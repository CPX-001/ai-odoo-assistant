# M4-10 — Gate de M4

## Contexto

- Ejecutar sólo después de M4-01..M4-09 verdes.
- Esta task no añade features. Verifica el milestone contra Source of Truth y decide PASS/FAIL/CONDITIONAL.
- Un fake Codex no es evidencia suficiente para el vertical slice final.

## Objetivo

Demostrar con evidencia ejecutable que Codex está integrado como `ReasoningEngine` sustituible y que el primer agentic `EXPLAIN` vertical slice respeta identidad, tools, evidence, budgets y citas sin introducir M5/M6.

## No debes implementar

- nuevas features para maquillar una gate fallida;
- QUERY/HOW_TO/RAG;
- writes/approvals/actions;
- conversation platform completa;
- provider selector genérico.

Si falla una comprobación, corrige sólo el defecto dentro de M4 o marca FAIL/CONDITIONAL indicando qué packet reabrir.

## Verificaciones obligatorias

### 1. Calidad/regresiones

- suite completa con Assistant DB real;
- Ruff;
- mypy;
- migraciones fresh + upgrade desde M3;
- addon Odoo 18 install/update/tests;
- M1 postgres/runtime/systemd/odoo/alternate smokes;
- M2 browser E2E;
- M3 source/log gate smokes relevantes.

### 2. App Server real

- runtime/SDK/version documentados;
- App Server arranca como usuario no-root del Assistant;
- handshake real;
- auth/model usable sin secretos gestionados por el Assistant;
- thread M4 efímero;
- cwd aislado;
- sandbox/approval policy comprobados;
- no subprocess huérfano tras turn/shutdown.

### 3. ReasoningEngine

- `CodexAppServerEngine` implementa el port sin imports Codex en application;
- `ContextPack` bounded/sanitized;
- `AnswerEnvelope` validado por schema;
- invalid/malformed output falla cerrado;
- Codex thread state no se usa como product memory.

### 4. ToolExecutor

- registry allowlisted per turn;
- sólo read/metadata;
- schema validation;
- budgets/deadline;
- unknown/duplicate/manipulated calls rechazadas;
- no `sudo`, shell libre, SQL Odoo, `execute_kw`/`execute_method`.

### 5. Source dynamic tools

- `find_symbol`, `find_model_extensions`, `read_excerpt` reales;
- refs/fingerprint M3 conservados;
- stale source no produce checked Evidence;
- no physical path input/output;
- excerpt causal del fixture disponible.

### 6. EXPLAIN/evidence

- current record se relee por ORM bajo usuario efectivo antes de reasoning;
- Evidence record + source están en ledger;
- final refs existen y corresponden a Evidence real;
- high confidence no sobrevive si falta el soporte exigido;
- proposed actions siguen prohibidas en M4;
- traces sanitizados.

### 7. Seguridad

- prompt injection no amplía tools/autoridad;
- built-in Codex filesystem/shell no se usa como evidence path;
- secrets canary no aparece en context/tool/output/browser/traces;
- frame/event/tool budgets bounded;
- timeout/interrupt limpia runtime;
- output HTML/citation tampering seguro.

### 8. Odoo/UI

- browser sólo habla con Odoo;
- identity/delegation siguen server-side;
- panel muestra answer/confidence/limitations/citations;
- XSS protegido;
- access denied y engine unavailable son errores controlados;
- M2 context-read no regresa.

### 9. E2E objetivo

Pregunta real desde `sale.order`:

`¿Por qué al confirmar este pedido se crea una tarea?`

Debe demostrarse:

- respuesta causal útil;
- identifica extensión `action_confirm` y creación de tarea del fixture;
- cita el pedido actual;
- cita module/logical file/lines/fingerprint source actuales;
- al menos un source tool roundtrip real de Codex;
- no se infiere PASS por mocks.

### 10. Readiness

Con DB/migrations/source/logs/reasoning realmente operativos:

- `/v1/admin/status` → `FULLY_READY`;
- Diagnostics muestra reasoning operational sanitizado.

Al retirar/desautenticar Codex:

- readiness → `DEGRADED`;
- runtime/Odoo siguen vivos;
- error accionable sin token/path leak.

## Reporte requerido

Crear `docs/M4_GATE_REPORT.md` con tabla como mínimo:

| Check | Resultado | Evidencia/comando |
| --- | --- | --- |
| pytest/lint/mypy | PASS/FAIL | ... |
| migrations/addon | PASS/FAIL | ... |
| M1-M3 regressions | PASS/FAIL | ... |
| Codex real handshake | PASS/FAIL | ... |
| structured output | PASS/FAIL | ... |
| ToolExecutor budgets | PASS/FAIL | ... |
| source dynamic tools | PASS/FAIL | ... |
| evidence/citations | PASS/FAIL | ... |
| security/injection | PASS/FAIL | ... |
| browser boundary | PASS/FAIL | ... |
| sale.order Codex E2E | PASS/FAIL | ... |
| FULLY_READY/degraded | PASS/FAIL | ... |

## Veredicto

Sólo finalizar con:

- `M4 GATE: PASS` si todo, incluido Codex real y E2E real, está demostrado;
- `M4 GATE: CONDITIONAL` si la implementación/tests deterministas son verdes pero falta una prueba real por ausencia de auth/runtime compatible;
- `M4 GATE: FAIL` si existe un defecto funcional/seguridad.

No avances a M5.

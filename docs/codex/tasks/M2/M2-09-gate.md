# M2-09 — Gate de M2

## Contexto

- Ejecutar sólo después de M2-01..M2-08.
- Esta task no añade features. Verifica UI/context/delegation contra el Source of Truth y decide PASS/FAIL.
- M1 debe seguir válido; no aceptar regresiones del runtime/install para declarar M2 completo.

## Objetivo

Demostrar con evidencia ejecutable que M2 permite preguntar desde un registro Odoo y releerlo bajo el usuario real mediante contexto y delegación firmada, sin bypass de permisos ni features adelantadas de M3+.

## No debes implementar

- nuevas features para maquillar una gate fallida;
- source/log providers;
- Codex/ReasoningEngine/agent loop;
- RAG/query engine;
- writes/approvals/actions.

Si una comprobación falla, corrige sólo el defecto dentro del scope M2 o marca FAIL e indica qué task debe reabrirse.

## Verificaciones obligatorias

### 1. Calidad y boundaries

- suite completa de tests;
- Ruff;
- mypy;
- `contracts` siguen libres de Odoo/FastAPI/storage;
- `application` no depende del adapter HTTP concreto;
- no `execute_kw`/`execute_method` genérico;
- no `sudo()` en caminos normales del agente;
- no SQL del Assistant Service contra Odoo.

### 2. Addon/UI

- addon instala y actualiza en Odoo 18 Community;
- panel/entrada del asistente aparece para un usuario interno soportado;
- form real produce `ScreenContext` con model/res_id correctos;
- pantalla sin registro se maneja sin inventar contexto;
- browser sólo llama a Odoo.

### 3. Identidad y delegación

- identidad efectiva deriva server-side;
- uid/company inyectados desde browser no son autoritativos;
- token firmado, versionado y con TTL corto;
- binding a turn + DB/instancia + user + companies + model/IDs + scopes;
- tampering/expiry/scope mismatch se rechazan;
- política de replay explícita y testeada.

### 4. ORM y permisos

- relectura sólo por ORM Odoo;
- ACL respetadas;
- record rules respetadas;
- restricted fields respetados;
- multi-company no permite escalada;
- otro model/id fuera del scope se rechaza antes de devolver datos.

### 5. OdooGateway

- adapter real implementa sólo metadata/read necesarios;
- endpoint/config Odoo es server-side y configurable;
- timeouts/size caps/redirect policy activos;
- token/secret no llegan a ReasoningEngine ni errores visibles.

### 6. Context-read service

- ingress autenticado Odoo → Assistant Service;
- service revalida schema/limits;
- registro se relee por gateway, no desde datos confiados de ScreenContext;
- respuesta M2 es determinista y no finge razonamiento LLM;
- traces no contienen mensajes crudos, tokens ni payload de registro completo.

### 7. E2E sale.order

Con Odoo + service reales:

- abrir pedido → abrir panel → preguntar → releer → mostrar resultado;
- `display_name`/estado mostrado corresponde al ORM actual;
- usuario no-admin/scope negativo no obtiene datos fuera de permisos;
- ninguna llamada browser → Assistant Service.

### 8. Regresión M1

- `/health` y `/v1/admin/status` siguen funcionales;
- addon Diagnostics sigue usable;
- Assistant DB/migrations siguen en head;
- cambios M2 no introducen acceso SQL a Odoo ni rompen loopback/bootstrap.

## Acceptance criteria final

Sólo marcar **PASS** si se demuestra:

1. UI contextual funciona en Odoo 18 real;
2. `ScreenContext` se captura sin identidad confiada;
3. identidad se deriva server-side;
4. delegación firmada y scoped protege cada lectura;
5. ORM ejecuta como usuario real y respeta ACL/record rules/fields/multi-company;
6. Assistant Service sólo usa el `OdooGateway` estrecho;
7. E2E `sale.order` funciona con service real;
8. browser no ve secrets/tokens/endpoints internos sensibles;
9. no existen features M3+ adelantadas;
10. tests/lint/type-check verdes y M1 sin regresión relevante.

## Resultado requerido de Codex

Crear `docs/M2_GATE_REPORT.md` únicamente al finalizar la gate y entregar una tabla equivalente a:

| Check | Resultado | Evidencia/comando |
| --- | --- | --- |
| tests | PASS/FAIL | ... |
| lint | PASS/FAIL | ... |
| type-check | PASS/FAIL | ... |
| addon install/upgrade | PASS/FAIL | ... |
| panel + ScreenContext | PASS/FAIL | ... |
| server-side identity | PASS/FAIL | ... |
| delegation tamper/expiry/scope | PASS/FAIL | ... |
| ACL/record rules/fields | PASS/FAIL | ... |
| multi-company | PASS/FAIL | ... |
| OdooGateway real | PASS/FAIL | ... |
| context-read API | PASS/FAIL | ... |
| sale.order E2E | PASS/FAIL | ... |
| browser boundary | PASS/FAIL | ... |
| M1 regression | PASS/FAIL | ... |

Finalizar con `M2 GATE: PASS`, `M2 GATE: FAIL` o `M2 GATE: CONDITIONAL` y la razón concreta.

Sólo si PASS:

- actualizar `README.md`, `docs/codex/MILESTONES.md` y `docs/codex/tasks/M2/README.md` como completados;
- dejar M3 como siguiente milestone;
- no iniciar M3 automáticamente.

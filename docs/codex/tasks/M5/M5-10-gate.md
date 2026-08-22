# M5-10 — Gate de M5

## Contexto

- Ejecutar sólo después de M5-01..M5-09 verdes.
- Esta task no añade features; verifica M5 contra el Source of Truth y decide PASS/FAIL/CONDITIONAL.
- No corregir una gate roja introduciendo capacidades de M6.

## Objetivo

Demostrar con evidencia ejecutable que QUERY, navegación/schema runtime y HOW_TO/RAG documental funcionan E2E bajo permisos reales, con retrieval/citas verificables y sin ampliar la autoridad read-only del producto.

## No debes implementar

- writes, previews, approvals o actions;
- nuevos providers/features para maquillar una comprobación fallida;
- embeddings/vector DB sin decisión arquitectónica previa;
- conversación persistente compleja;
- Odoo 19.

Si falla una comprobación, corrige sólo el defecto dentro de M5 o marca FAIL/CONDITIONAL e indica qué packet reabrir.

## Verificaciones obligatorias

### 1. Calidad y regresiones

- suite completa con Assistant DB real;
- Ruff y mypy;
- Alembic fresh + upgrade desde M4 + idempotencia;
- addon Odoo 18 install/update/tests;
- smokes relevantes M1 runtime/install;
- M2 identidad/delegación/browser;
- M3 source/logs;
- M4 Codex/EXPLAIN/security/E2E sin regresiones.

### 2. Effective schema

- schema procede de Odoo bajo usuario efectivo;
- fields no autorizados no aparecen/no son utilizables;
- types/operators/capabilities gobiernan validación QUERY;
- no listas versionadas/hardcodeadas de modelos/fields;
- metadata malformada falla cerrado.

### 3. Navegación

- menús/actions visibles se resuelven como usuario real;
- rutas ocultas no se filtran;
- no se ejecutan actions ni contexts/domains arbitrarios;
- Evidence/citas de navegación son lógicas y sanitizadas.

### 4. QUERY authority + ORM

- la autoridad QUERY no ensancha tokens M2 existentes implícitamente;
- replay/scope/model/company bindings efectivos;
- search/filter/order bounded;
- aggregations/grouping allowlisted y bounded;
- ORM `su=False`, ACL, record rules y field access demostrados;
- no direct Odoo SQL, generic method execution ni raw executable domains;
- empty result es citable;
- truncation/limits se representan correctamente.

### 5. QUERY agent loop

- registry per-turn least privilege;
- Codex real solicita tool(s) QUERY;
- ToolExecutor valida schema/budgets;
- answer refs resuelven sólo a Evidence checked;
- manipulated args/refs/output fallan cerrado;
- `proposed_action` prohibida.

### 6. Knowledge ingestion/FTS

- ingesta fresh, incremental e idempotente;
- changed/removed documents actualizan vigencia correctamente;
- fingerprints/chunks reproducibles;
- PostgreSQL FTS operativo con índices;
- root/layout configurable y escape/symlink bloqueados;
- no embeddings/vector DB ni web fetching.

### 7. Knowledge retrieval

- `knowledge.search` bounded;
- `knowledge.read_excerpt` revalida ref/fingerprint vigente;
- stale/missing no produce Evidence checked;
- physical paths no son input/output del modelo/browser;
- contenido documental adversarial no cambia policy/tools.

### 8. HOW_TO

- Codex real usa knowledge retrieval;
- respuesta usa facts reales de navegación/schema cuando afirma pasos específicos;
- menú/field ausente no se inventa;
- documentación y facts de instalación tienen citas válidas;
- confidence se degrada cuando falta soporte;
- no acciones automáticas ni writes.

### 9. UI/security/readiness

- browser sólo habla con Odoo;
- routing no mezcla registries/authority entre EXPLAIN, QUERY y HOW_TO;
- XSS/HTML/Markdown adversarial seguro;
- secrets canary ausente en context browser-facing/traces;
- timeouts/budgets/cleanup efectivos;
- capabilities M5 se diagnostican sin romper el significado previo de readiness salvo cambio explícitamente autorizado por SoT/ADR.

### 10. E2E real

El reporte M5 debe demostrar al menos:

- un QUERY real con resultado exacto fixture;
- un registro oculto por permisos que no aparece;
- un HOW_TO real con navegación/schema/documento fixture;
- al menos un roundtrip real de QUERY tool y uno de knowledge tool con Codex;
- citas/fingerprints actuales;
- negativos de scope/stale/auth/runtime;
- cleanup del entorno desechable.

## Reporte requerido

Crear `docs/M5_GATE_REPORT.md` con tabla mínima:

| Check | Resultado | Evidencia/comando |
| --- | --- | --- |
| pytest/lint/mypy | PASS/FAIL | ... |
| migrations/addon | PASS/FAIL | ... |
| M1-M4 regressions | PASS/FAIL | ... |
| effective schema | PASS/FAIL | ... |
| navigation metadata | PASS/FAIL | ... |
| QUERY authority/ORM | PASS/FAIL | ... |
| QUERY Codex E2E | PASS/FAIL | ... |
| knowledge ingestion/FTS | PASS/FAIL | ... |
| knowledge retrieval | PASS/FAIL | ... |
| HOW_TO Codex E2E | PASS/FAIL | ... |
| security/browser | PASS/FAIL | ... |
| no M6 capabilities | PASS/FAIL | ... |

## Veredicto

Finalizar únicamente con:

- `M5 GATE: PASS` si todo, incluidos QUERY y HOW_TO reales con Codex, está demostrado;
- `M5 GATE: CONDITIONAL` si implementación/tests deterministas son verdes pero una comprobación real no puede ejecutarse por ausencia externa de auth/runtime compatible;
- `M5 GATE: FAIL` si existe defecto funcional, de evidencia o seguridad.

No avances a M6.

# M5 — QUERY + HOW_TO + RAG

Estado: **M5-01 a M5-07 implementadas y verificadas; M5-08 es la siguiente task.**

M5 empieza únicamente después de **M4 GATE: PASS**. Su objetivo es ampliar el vertical slice de sólo lectura para que el asistente pueda:

1. ejecutar consultas server-side acotadas sobre Odoo bajo el usuario efectivo (`QUERY`);
2. explicar cómo realizar tareas reales en esa instalación usando navegación, schemas runtime y conocimiento indexado (`HOW_TO`);
3. recuperar documentación mediante PostgreSQL FTS y convertirla en Evidence comprobable, sin saltar prematuramente a embeddings ni vector DB.

Fuente de verdad: `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT_CONFIG.md`, `AGENTS.md`, `service/AGENTS.md`, `addons/AGENTS.md`, `tests/AGENTS.md` y el estado real dejado por M0-M4. Antes de implementar cada packet debe contrastarse de nuevo con el Source of Truth.

## Resultados observables

### QUERY

Ejemplo objetivo:

```text
usuario está en res.partner y pregunta por sus facturas abiertas
    ↓
Odoo deriva identidad/compañías/delegación server-side
    ↓
Assistant obtiene schema efectivo del modelo objetivo
    ↓
Codex solicita una query mediante tools explícitas
    ↓
ToolExecutor valida schema + policy + budgets
    ↓
Odoo ejecuta ORM bajo el usuario real, sin sudo/SQL libre
    ↓
Evidence(record/metadata) checked
    ↓
AnswerEnvelope QUERY con evidence_refs válidos
    ↓
panel muestra respuesta y citas sanitizadas
```

### HOW_TO

Ejemplo objetivo:

```text
usuario pregunta cómo configurar plazos de pago
    ↓
Assistant consulta navegación visible + schemas runtime
    ↓
knowledge.search usa PostgreSQL FTS
    ↓
knowledge.read_excerpt revalida documento/fingerprint
    ↓
Codex combina Evidence de menú/schema/documentación
    ↓
AnswerEnvelope HOW_TO con pasos adaptados a la instalación
    ↓
panel muestra guía + citas sin inventar menús/campos ausentes
```

## Orden de ejecución

1. [`M5-01-effective-runtime-schema.md`](M5-01-effective-runtime-schema.md) — schema efectivo por usuario/policy y contratos runtime.
2. [`M5-02-navigation-metadata.md`](M5-02-navigation-metadata.md) — navegación, acciones y superficies visibles de la instalación.
3. [`M5-03-safe-query-orm.md`](M5-03-safe-query-orm.md) — autoridad QUERY y primitives ORM acotadas de búsqueda/agregación.
4. [`M5-04-query-tools-workflow.md`](M5-04-query-tools-workflow.md) — dynamic tools QUERY, orquestación y citas.
5. [`M5-05-knowledge-ingestion-fts.md`](M5-05-knowledge-ingestion-fts.md) — documentos, chunks, fingerprints e índice PostgreSQL FTS incremental.
6. [`M5-06-knowledge-retrieval-tools.md`](M5-06-knowledge-retrieval-tools.md) — búsqueda/excerpts DOCUMENT con Evidence checked.
7. [`M5-07-how-to-workflow.md`](M5-07-how-to-workflow.md) — orquestación HOW_TO con navegación + schema + knowledge.
8. [`M5-08-panel-routing-security.md`](M5-08-panel-routing-security.md) — integración read-only multi-workflow, UI, readiness y hardening.
9. [`M5-09-real-e2e-query-how-to.md`](M5-09-real-e2e-query-how-to.md) — E2E real de QUERY y HOW_TO con Codex/Odoo 18.
10. [`M5-10-gate.md`](M5-10-gate.md) — gate integral y cierre de M5.

Ejecutar **una sola task cada vez** y no avanzar automáticamente a la siguiente sin verificar sus acceptance criteria.

## Invariantes de M5

- M5 sigue siendo **read-only**. No implementa writes, previews de write, approvals ni business actions de M6.
- Odoo conserva autoridad de identidad, ACL, record rules, field access, compañías y reglas de negocio.
- El Assistant Service no recibe credenciales SQL de Odoo y no consulta su DB directamente.
- No `sudo()`, shell libre, SQL libre, Python arbitrario, `execute_kw`, `execute_method` ni nombres de métodos controlados por el modelo.
- Las queries del modelo son estructuras tipadas y bounded; nunca un domain Python/string arbitrario ni una expresión que Odoo ejecute sin validación.
- Los modelos/campos/operadores/order/grouping se validan contra policy y schema efectivo antes de ejecutar.
- El token M2 de lectura exacta no se ensancha implícitamente. La autoridad QUERY debe ser explícita, limitada al turn y compatible con replay protection.
- Los schemas se descubren en runtime; no crear `SaleOrder18`, `AccountMove18`, listas de campos por versión ni branches de major en `application`.
- Navegación y acciones se obtienen de la instalación real bajo el usuario efectivo; no hardcodear rutas de menú como conocimiento del producto.
- Knowledge usa primero retrieval lexical/estructural con PostgreSQL FTS, tal como fija la arquitectura. Embeddings/vector search quedan fuera salvo nueva evidencia/ADR.
- Knowledge roots/providers son configuración validada; no escanear el host entero ni acceder a paths libres entregados por el modelo.
- No realizar fetching web automático durante un turn M5.
- Records, schemas, menús y documentos son **datos no confiables** frente a prompt injection.
- `AnswerEnvelope.evidence_refs` sólo puede resolver a Evidence realmente producida/validada en ese turn.
- Una respuesta de alta confianza no puede sobrevivir si falta la evidencia requerida para sus afirmaciones verificables.
- El browser sigue hablando únicamente con Odoo; identidad, delegación, shared secrets y rutas internas permanecen server-side.
- Codex continúa como adapter sustituible; M5 no introduce lógica de producto dentro del protocolo App Server.
- `EXPLAIN` de M4 debe seguir funcionando sin regresiones.

## Gate de M5

M5 sólo se considera terminado cuando, como mínimo:

- existe un schema efectivo runtime que excluye campos/modelos no autorizados y gobierna validación QUERY;
- navegación visible puede resolverse bajo el usuario real y citarse sin inventar rutas;
- QUERY puede buscar, filtrar, ordenar y realizar agregaciones acotadas mediante ORM sin ampliar autoridad;
- record rules, field access y multi-company se conservan en queries reales;
- una query vacía produce evidencia verificable del resultado vacío en lugar de una afirmación sin soporte;
- documentos configurados se ingieren incrementalmente con fingerprint y chunks reproducibles;
- PostgreSQL FTS devuelve candidatos bounded y `read_excerpt` revalida la versión actual del documento;
- HOW_TO puede construir una guía usando navegación/schema/documentación de la instalación y citarla;
- documentos/records/metadata adversariales no pueden ampliar tools, autoridad ni revelar canaries;
- el panel soporta los workflows M5 previstos sin acceso browser → Assistant ni XSS;
- existe E2E real con Codex para al menos un QUERY y un HOW_TO sobre Odoo 18;
- M1-M4 no regresan y suite, Ruff, mypy, migraciones y addon tests permanecen verdes;
- no se ha implementado ninguna capacidad de M6.

Un fake ReasoningEngine es válido para tests deterministas, pero no basta para declarar el gate final si el host de gate dispone del runtime real requerido. Si Codex real no puede probarse por ausencia de auth/runtime compatible, el reporte debe distinguir claramente implementación verde de verificación real pendiente.

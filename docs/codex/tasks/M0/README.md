# M0 — Repo y contratos

Estado: **DONE**. La gate M0-06 está superada; M1 todavía no se ha iniciado.

Objetivo del milestone: crear el esqueleto ejecutable mínimo del monorepo, los contratos y ports base, y una baseline de tests/lint/type-checking sin implementar features del producto.

Fuente de verdad: `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`, especialmente §§23, 24, 27, 29, 30 y 34.3.

## Orden de ejecución

1. [`M0-01-python-package-baseline.md`](M0-01-python-package-baseline.md) — package Python y toolchain mínima.
2. [`M0-02-core-contracts.md`](M0-02-core-contracts.md) — `ScreenContext`, `RecordRef`, `Evidence`.
3. [`M0-03-agent-contracts.md`](M0-03-agent-contracts.md) — `ContextPack`, `ToolSpec`, `AnswerEnvelope` y tipos auxiliares mínimos.
4. [`M0-04-ports.md`](M0-04-ports.md) — `ReasoningEngine`, `OdooGateway`, `LogProvider`.
5. [`M0-05-schema-and-boundary-tests.md`](M0-05-schema-and-boundary-tests.md) — JSON Schema y tests de boundaries.
6. [`M0-06-gate.md`](M0-06-gate.md) — verificación integral y cierre de M0.

Ejecutar una sola task cada vez. Antes de cada una, Codex debe inspeccionar el estado real del repo y leer `AGENTS.md`, `service/AGENTS.md`, `tests/AGENTS.md`, `docs/ARCHITECTURE.md` y este task packet.

## Gate de M0

M0 sólo se considera terminado cuando:

- existe el package del Assistant Service bajo `service/`;
- los contratos mínimos públicos son Pydantic y exportan JSON Schema;
- existen los ports mínimos sin adapters concretos;
- los imports respetan las boundaries documentadas;
- `pytest`, lint y type-check pasan;
- no se ha implementado FastAPI, PostgreSQL, Odoo addon funcional, scanner, Codex App Server ni otras features de M1+.

Tras superar esta gate, el siguiente milestone es M1 — Runtime/install.

## Resultado de la gate M0-06

- 34 tests superados.
- 16 JSON Schemas públicos generados de forma determinista y serializable.
- Ruff y mypy estricto superados.
- Boundaries de `contracts`, `ports`, `application` condicional y clases versionadas verificadas por AST.
- Sin FastAPI, PostgreSQL, addon funcional, scanner, retrieval, providers concretos de logs ni adapter de Codex.

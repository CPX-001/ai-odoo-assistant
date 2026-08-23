# M5 gate report

Fecha: 2026-08-23.

| Check | Resultado | Evidencia/comando |
| --- | --- | --- |
| pytest/lint/mypy | PASS | `installer/smoke/m1_gate.sh quality`: 362 passed, 33 opt-in skipped; Ruff y mypy verdes |
| migrations/addon | PASS | Assistant DB real: 30 tests de migraciones/persistencia; el runner M5 instala addon + fixture en Odoo 18 fresh |
| M1-M4 regressions | PASS | Suite completa verde, M4 gate versionada PASS y spot-check real actual Odoo→Assistant 200; router M4 actualizado a `/turn` + `EXPLAIN` |
| effective schema | PASS | Tests application/adapters; E2E obtiene schema real antes del aggregate y cita schema HOW_TO |
| navigation metadata | PASS | Ruta fixture visible comprobada bajo usuario real; sin `sudo()` ni ejecución de action/context/domain |
| QUERY authority/ORM | PASS | Token q1 separado, bindings/replay/budgets testeados; E2E A=2/B=1 bajo record rule |
| QUERY Codex E2E | PASS | Codex real llamó `odoo.get_effective_schema` → `odoo.aggregate_records`; write terminó `query_rejected` |
| knowledge ingestion/FTS | PASS | PostgreSQL real: fresh/incremental/retirement; E2E indexó 1 documento/1 chunk y retiró 1 documento |
| knowledge retrieval | PASS | `knowledge.search` lexical bounded + `knowledge.read_excerpt` vigente; fingerprint retirado no reutilizado |
| HOW_TO Codex E2E | PASS | Citas reales `navigation` + `schema` + `document`; guía coherente con menú y `guide_code` fixture |
| security/browser | PASS | Browser→Odoo solamente, registries disjuntos, XSS adversarial, canaries/paths/secrets ausentes, cleanup efectivo |
| no M6 capabilities | PASS | Registries exactos read-only; ACTION/write/shell/SQL/Python/método genérico ausentes |

## Decisiones y observaciones

- `FULLY_READY` conserva su significado M4. QUERY/navigation/knowledge/HOW_TO se
  exponen como capabilities diagnósticas sanitizadas y no alteran la fórmula.
- El adapter Codex fija instrucciones por workflow sólo para QUERY/HOW_TO. En
  QUERY exige schema antes del ORM; en HOW_TO explica la semántica AND de FTS y
  la revalidación del excerpt. Software determinista sigue validando tools,
  Evidence, citas, budgets y rechazo de proposed actions.
- Una repetición opt-in de M4 alcanzó respuestas 200 seguras, aunque el proveedor
  no eligió cita source en ese muestreo; la gate M4 completa ya versionada y las
  regresiones deterministas siguen verdes. No se relajaron sus validadores ni
  budgets para maquillar variabilidad del modelo.
- El repaso del navegador integrado confirmó que el host Odoo local responde;
  la aceptación funcional del panel se hizo sobre la instancia desechable del
  runner Chromium, no sobre datos DEV.

## Veredicto

**M5 GATE: PASS**

No se avanza a M6.

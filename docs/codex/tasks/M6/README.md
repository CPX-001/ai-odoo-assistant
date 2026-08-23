# M6 — ACTION segura

Estado: **M6-01..M6-10 implementados; gate técnico real verde, pero M6 GATE permanece FAIL por una desviación de alcance frente al Source of Truth. M6-11..M6-13 están preparados para cerrar esa desviación.**

El E2E real Odoo 18 + Assistant PostgreSQL + Codex + Chromium ya está verificado. El blocker pendiente no es infraestructura: el Source of Truth exige `create/update` seguro y al menos una business action curada, mientras M6-01..10 implementaron únicamente el slice de update `record_patch`. Ver [`docs/M6_GATE_REPORT.md`](../../../M6_GATE_REPORT.md).

M6 empieza después de **M5 GATE: PASS** y no puede considerarse cerrado hasta que M6-13 vuelva a ejecutar el gate completo y el check de Source of Truth sea PASS.

Fuente de verdad: `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT_CONFIG.md`, `AGENTS.md`, `service/AGENTS.md`, `addons/AGENTS.md`, `tests/AGENTS.md` y el estado real dejado por M0-M5.

## Flujo obligatorio

Toda operación con side effects conserva:

```text
proposal → preview → approval → commit → verification
```

El ReasoningEngine puede ayudar a construir una proposal y solicitar previews host-controlled. Nunca recibe autoridad de approval/commit. El browser sólo habla con Odoo y no aporta identidad ni payload ejecutable autoritativo.

## Task packets

### Base ACTION ya implementada

1. [`M6-01-action-contracts-policy.md`](M6-01-action-contracts-policy.md) — contratos ACTION, payload canónico y policy base.
2. [`M6-02-effective-write-schema.md`](M6-02-effective-write-schema.md) — schema efectivo de escritura y validación de cambios soportados.
3. [`M6-03-preview-pipeline.md`](M6-03-preview-pipeline.md) — preview real bajo usuario, diff y precondition fingerprint sin mutar Odoo.
4. [`M6-04-approval-persistence.md`](M6-04-approval-persistence.md) — persistencia, binding, expiración y state machine de approvals.
5. [`M6-05-action-authority-commit.md`](M6-05-action-authority-commit.md) — autoridad ACTION separada y commit ORM estrecho.
6. [`M6-06-verification-audit.md`](M6-06-verification-audit.md) — relectura, verification receipt y auditoría.
7. [`M6-07-action-workflow-tools.md`](M6-07-action-workflow-tools.md) — workflow ACTION con Codex y preview, nunca commit autónomo.
8. [`M6-08-panel-approval-security.md`](M6-08-panel-approval-security.md) — UX de preview/approve/cancel y hardening browser→Odoo.
9. [`M6-09-real-e2e-action.md`](M6-09-real-e2e-action.md) — E2E real Codex/Odoo/Chromium y casos adversariales.
10. [`M6-10-gate.md`](M6-10-gate.md) — primer gate integral; técnicamente verde pero FAIL por scope del Source of Truth.

### Closure packets pendientes

11. [`M6-11-safe-record-create.md`](M6-11-safe-record-create.md) — `record_create` seguro, approved, verificado e idempotente ante respuesta ambigua.
12. [`M6-12-curated-business-action.md`](M6-12-curated-business-action.md) — una business action real explícitamente allowlisted, con preview/approval/authority/idempotencia/verification propias.
13. [`M6-13-source-of-truth-final-gate.md`](M6-13-source-of-truth-final-gate.md) — repetir el gate completo contra el Source of Truth y cerrar M6 sólo si create + update + curated action quedan demostrados.

Cada packet es un contrato de aceptación independiente aunque se ejecute dentro de un Goal compartido.

## Goal Mode

Los Goals históricos M6-01..10 ya fueron ejecutados. Para cerrar el milestone queda **un único Goal recomendado**:

### Goal E — cierre Source of Truth

Ejecutar juntos, secuencialmente:

**M6-11 + M6-12 + M6-13**

Tiene sentido agruparlos porque comparten exactamente el mismo objetivo pendiente:

```text
safe create
    ↓
curated business action
    ↓
full Source-of-Truth gate
```

M6-11 y M6-12 deben completarse y testearse individualmente antes de iniciar M6-13. M6-13 no puede modificar/relajar requisitos sólo para conseguir PASS.

Prompt base recomendado:

```text
Implement M6-11, M6-12 and M6-13 sequentially.
Treat every packet as an independent acceptance contract.
Complete and verify one packet before continuing to the next.
Run each packet's mandatory tests after that packet, then run the combined regression suite and the real M6 gate at the end.
Do not weaken existing M6 security invariants or replace the Source of Truth requirement with a smaller scope.
Reuse the existing proposal → preview → approval → commit → verification architecture; do not build a parallel write system.
Do not implement M7 or M8 work.
```

## Invariantes de M6

- `proposal → preview → approval → commit → verification` es obligatorio para patch, create y curated actions.
- `ProposedAction` y texto de Codex son intención/presentación, nunca authority.
- Codex no recibe approval, commit, raw `write`, raw `create` ni business-action execute tools.
- Browser nunca entrega identidad ni payload de side effect autoritativo; sólo proposal id + decisión mínima cuando corresponda.
- Odoo deriva identidad y ejecuta ORM/business rules bajo usuario real con `su=False`.
- M2/v1, QUERY/q1 y authorities ACTION permanecen explícitas, bounded, separadas y replay-protected.
- Approval queda ligada al payload canónico, actor, database, companies, policy/schema/action revision, target/preconditions y expiry.
- Stale state/revision/reference debe fallar cerrado o requerir nueva preview/approval.
- No `sudo()`, SQL directo del Assistant contra Odoo, shell/Python arbitrario, `execute_method`, `execute_kw`, reflection dinámica ni context/method names controlados por el modelo.
- `record_create` debe ser seguro contra duplicados ante timeout/respuesta perdida post-commit.
- Business actions usan handlers explícitamente allowlisted con semántica de idempotencia/side effects definida y verificable.
- Ningún retry ambiguo puede repetir un side effect a ciegas.
- Success sólo tras reread/outcome verification bajo el mismo usuario.
- Audit no almacena secrets, authority tokens completos, DSNs ni tracebacks crudos.
- EXPLAIN, QUERY y HOW_TO no amplían sus registries ni risks.
- No introducir M7 Settings/product hardening ni M8/Odoo 19 dentro de M6.

## Scope del cierre

Al acabar M6 debe existir como mínimo:

- **safe update**: `record_patch` bounded de un registro;
- **safe create**: `record_create` bounded de un registro;
- **una curated business action real** con handler explícito;
- preview sin side effects;
- approval explícita;
- authority one-shot;
- ORM/action bajo usuario real;
- protection contra replay/tampering/stale/response ambiguity;
- verification Evidence + audit;
- E2E real con Odoo 18 + Codex + Chromium.

Siguen fuera de scope salvo requirement explícito nuevo:

- delete/unlink genérico;
- bulk/multi-record writes/creates/actions;
- x2many command lists arbitrarias;
- arbitrary methods/actions;
- autonomous approvals/commits;
- M7 product hardening;
- M8 Odoo 19.

## Gate final

M6 sólo se marca completado si **M6-13** actualiza `docs/M6_GATE_REPORT.md` a `M6 GATE: PASS` con evidencia reproducible de:

- suite/Ruff/mypy/migrations/addon verdes;
- M1-M5 sin regresiones;
- Source of Truth scope PASS;
- update/create/business action reales;
- ACL/record rules/field/company enforcement;
- approval/replay/tampering/stale/expiry;
- idempotencia de create y business action frente a respuesta ambigua;
- Codex sin commit authority;
- browser→Odoo solamente;
- success sólo tras verification;
- E2E real Odoo 18 + Codex + Chromium;
- ausencia de capabilities M7/M8 fuera de scope.

Hasta entonces **M6 permanece abierto y no se avanza a M7**.

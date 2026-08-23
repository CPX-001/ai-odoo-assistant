# M6-13 — Source of Truth final gate

Estado: **completada; M6 GATE: PASS** (2026-08-23). Evidencia reproducible en
`docs/M6_GATE_REPORT.md`.

## Contexto

- Requiere M6-11 y M6-12 implementadas y verificadas.
- El gate M6 previo quedó técnicamente verde salvo por la desviación de alcance frente al Source of Truth.
- Esta task no añade features nuevas salvo fixes estrictamente necesarios para cerrar defects encontrados durante el gate.
- El objetivo es demostrar que M6 satisface finalmente el scope completo exigido: `create/update` seguro + al menos una business action curada, además de todas las invariantes de seguridad ya verificadas.

## Objetivo

Repetir el gate integral M6 sobre el estado real del repo y actualizar `docs/M6_GATE_REPORT.md` con un veredicto inequívoco `PASS`, `CONDITIONAL` o `FAIL` basado en evidencia reproducible, incluyendo `record_patch`, `record_create` y la curated business action real.

M6 sólo puede cerrarse si el Source of Truth y la implementación dejan de contradecirse.

## Antes de editar

1. Lee íntegramente:
   - Source of Truth;
   - `docs/ARCHITECTURE.md`;
   - `AGENTS.md` y AGENTS locales;
   - `docs/M6_GATE_REPORT.md` actual;
   - M6-01..M6-13;
   - documentación M6 de contracts/action workflow.
2. Inspecciona código real, no los resúmenes de las tasks.
3. Comprueba que no se resolvió el blocker mediante un ADR/SOT que cambie requirements sin que esta task lo sepa.
4. Lista cualquier drift documental antes de cambiar estados.
5. No rebajes tests, policy, caps ni security invariants para obtener PASS.

## Checks obligatorios

### 1. Quality / static / regressions

Ejecutar y documentar:

- suite completa;
- Ruff;
- mypy;
- migrations fresh + upgrade;
- addon fresh install + update;
- M1-M5 regressions/gates relevantes;
- tests M6 previos.

Documentar counts reales y razón de cada skip.

### 2. Scope Source of Truth

Demostrar explícitamente:

- safe `update` existe y sigue siendo bounded (`record_patch`);
- safe `create` existe (`record_create`);
- existe al menos una business action real curada en producto;
- create/update/business action usan proposal → preview → approval → commit → verification;
- ninguna de esas operaciones expone un método/ORM genérico al modelo;
- no hay contradicción restante con el scope M6 del Source of Truth.

Este check debe ser `PASS` para cerrar M6. Si el Source of Truth exige algo adicional descubierto durante la revisión, no lo ignores: documenta FAIL y lo que falta.

### 3. Contracts / canonicalization

Para patch/create/business action:

- payloads versionados, strict, extra-forbid y bounded;
- fingerprint canónico estable;
- actor/database/company/policy/schema/action revisions ligados;
- target/fields/values/action tampering detectados;
- browser/model cannot supply authority.

### 4. Effective schemas / policy

Demostrar:

- read/write/create eligibility bajo usuario real;
- fields/models sensibles bloqueados;
- relation/type rules respetadas;
- revisions revalidadas antes de commit;
- QUERY no se amplía accidentalmente;
- no version classes/checks en application.

### 5. Preview sin efectos

Para las tres familias ACTION:

- preview no muta Odoo;
- record_patch muestra before/after real;
- record_create distingue requested values de defaults/computed post-create;
- curated business action muestra target/state/outcome esperado/warnings;
- Evidence checked y sanitizada;
- stale/revision/reference changes invalidan cuando corresponde.

### 6. Approval/state machine

Demostrar:

- approval durable y ligada al payload exacto;
- approve/reject/expiry/concurrency/cross-user/cross-company/replay/tampering;
- reject/cancel siempre cero side effects;
- browser sólo envía proposal id + decisión mínima;
- actor se deriva en Odoo.

### 7. Commit authorities

Demostrar:

- preview authority, patch/create/action authority y q1/v1 están separadas según contratos;
- write/action authority sólo existe después de approval;
- TTL/bindings/one-shot/replay correctos;
- `su=False` y permisos reales revalidados justo antes del side effect;
- ningún endpoint recibe method/context/kwargs/domain libre;
- no generic `execute_method`, `execute_kw`, raw `write`, raw `create` ni reflection dinámica.

### 8. Create idempotency

Caso obligatorio con respuesta ambigua:

1. Odoo realiza create;
2. se pierde la respuesta;
3. recovery/retry ocurre;
4. el número de registros creados sigue siendo exactamente 1;
5. se recupera/verifica el resultado original.

Si no puede demostrarse, M6 = FAIL.

### 9. Business action idempotency

Caso obligatorio con respuesta ambigua/double-submit:

- la curated action se ejecuta como máximo una vez para el mismo approved attempt;
- retry/recovery verifica receipt/outcome antes de repetir;
- side effects observables no se duplican;
- stale o action ya ejecutada por otro actor se representa correctamente según la spec.

### 10. Verification / audit

Para patch/create/business action:

- success sólo tras reread/outcome check;
- Evidence checked refleja resultado real;
- `execution_unknown`/`unverified` si no se puede confirmar;
- audit reconstruye proposal → approval → attempt → verification;
- no secrets, raw authority tokens, DSNs, canaries o tracebacks crudos.

### 11. ReasoningEngine / tool boundaries

Demostrar:

- ACTION registry contiene sólo schema/preview tools necesarias;
- Codex puede proponer/solicitar previews soportadas;
- Codex **no tiene commit/approval/execute authority**;
- EXPLAIN/QUERY/HOW_TO registries siguen separados;
- proposed_action inventada, proposal id cruzada, payload/fingerprint falso o action id no allowlisted fallan cerrado;
- approve/execute no consulta otra vez al LLM qué payload usar.

### 12. Browser/UI/security

Con Chromium real:

- patch: diff exacto visible antes de aprobar;
- create: model/requested values/warnings visibles antes de aprobar;
- curated action: target/action/outcome esperado/warnings visibles;
- approval explícita;
- reject/cancel cero side effects;
- double-click protegido;
- stale exige nueva preview;
- XSS escapado;
- no secrets en DOM/console/responses;
- browser → Odoo solamente.

### 13. Real E2E Odoo 18 + Codex + Chromium

Ejecutar como mínimo:

#### Update

- happy approved patch → verified;
- no approval/reject → no write;
- ACL/record-rule denied → no leak/no write.

#### Create

- natural request → Codex/preview → approve → exactly one create → verified;
- reject/no approval → zero create;
- ACL/model/field/company denied → zero create;
- timeout after commit → exactly one record after recovery.

#### Curated business action

- natural request → Codex/preview → approve → action real → verified outcome;
- reject/no approval → no action;
- ACL/rule/state/stale denied → no action;
- replay/double-click/response loss → no duplicated side effects.

#### Adversarial

- prompt injection requesting shell/SQL/Python/arbitrary Odoo methods;
- method/action id tampering;
- proposal/approval cross-user/company;
- expiry/replay;
- XSS/content injection;
- browser payload extras.

Registrar counts esperados/observados de creates, writes y curated action executions.

### 14. Scope containment

Confirmar que M6 no introdujo accidentalmente:

- delete/unlink genérico;
- bulk/multi-record writes/creates/actions;
- arbitrary x2many commands;
- shell/SQL/Python arbitrario;
- generic model method execution;
- autonomous approval/commit;
- Settings/admin product hardening propio de M7;
- Odoo 19 branches en application.

## Gate report

Reemplaza/actualiza `docs/M6_GATE_REPORT.md` con evidencia actual, no añadas un segundo reporte ambiguo.

La tabla debe incluir al menos:

- quality/lint/mypy;
- migrations/addon;
- M1-M5 regressions;
- Source of Truth scope;
- contracts/canonicalization;
- schemas/policy;
- patch preview/commit/verification;
- create preview/commit/idempotency/verification;
- curated business action preview/commit/idempotency/verification;
- approval/state machine;
- reasoning/tool boundaries;
- browser/security;
- real E2E;
- audit;
- scope containment.

Documentar versiones Odoo/PostgreSQL/Codex/Chromium relevantes y comandos reproducibles sanitizados.

## Veredicto

- `PASS`: todos los requirements M6 del Source of Truth y todos los checks obligatorios disponibles están verdes, incluido E2E real requerido.
- `CONDITIONAL`: sólo falta una verificación externa obligatoria no disponible; no puede usarse para un requirement funcional no implementado.
- `FAIL`: existe requirement sin implementar, security failure, regression o contradicción real.

No usar PASS si:

- create puede duplicarse tras respuesta perdida;
- curated action puede repetir side effects por replay/retry;
- Codex puede ejecutar/commitear directamente;
- browser puede sustituir payload;
- write/create/action ocurre antes de approval;
- ACL/record rules/company no se preservan;
- success no está verificado;
- Source of Truth scope sigue discrepando.

## Actualización documental si PASS

Sólo si el gate final es PASS:

1. actualizar `docs/codex/tasks/M6/README.md` a M6-01..M6-13 completados / gate PASS;
2. actualizar `docs/codex/MILESTONES.md` a M0-M6 completados; M7 siguiente;
3. actualizar `docs/codex/README.md` para apuntar M7 como siguiente milestone aún no iniciado;
4. actualizar README raíz eliminando estados M6 obsoletos;
5. corregir cualquier mención antigua de “E2E pendiente” o “M6-01..03 solamente”.

No redactar ni implementar M7 dentro de esta task.

## Acceptance criteria

- `docs/M6_GATE_REPORT.md` refleja el estado actual y no el gate previo;
- Source of Truth scope = PASS o M6 permanece abierto;
- create/update + curated business action demostrados E2E;
- seguridad/authority/idempotency/verification completas;
- regresiones verdes;
- documentación consistente con el veredicto;
- M7 no iniciado.

## Después

1. Informa veredicto y evidencia real.
2. Si PASS, deja el repo administrativamente listo para redactar M7 en una instrucción posterior.
3. Si FAIL/CONDITIONAL, lista exactamente qué queda sin esconderlo detrás de un status genérico.

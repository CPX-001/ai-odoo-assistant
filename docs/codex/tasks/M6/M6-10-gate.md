# M6-10 — Gate integral ACTION segura

Estado: **implementado; gate técnico real verde el 2026-08-23, con veredicto global FAIL por la desviación formal de scope documentada en `docs/M6_GATE_REPORT.md`.**

## Contexto

- Requiere M6-01..M6-09 implementadas y verificadas.
- M6 no se considera completado por tener una UI de aprobación o un `write()` funcionando aisladamente.
- El gate debe demostrar el flujo completo `proposal → preview → approval → commit → verification`, sus boundaries de seguridad y la ausencia de regresiones M1-M5.

## Objetivo

Ejecutar y documentar el gate final de M6 sobre el estado real del repositorio, incluyendo suite determinista, migrations/addon, Odoo 18 real, Assistant PostgreSQL, Codex real cuando esté disponible, Chromium y casos adversariales de approval/write.

## Antes de editar

1. Lee de nuevo Source of Truth, `docs/ARCHITECTURE.md`, `AGENTS.md` y todos los packets M6.
2. Inspecciona el código real y no des por cumplida una requirement sólo porque la task anterior lo diga.
3. Lista cualquier desviación/ADR pendiente.
4. No modifiques tests, policy o límites sólo para hacer pasar el gate sin justificar el cambio contra la arquitectura.

## Checks obligatorios

### 1. Calidad y regresiones

- suite completa del service/addon/tests;
- Ruff;
- mypy;
- migrations fresh + upgrade;
- addon install/update fresh;
- M1-M5 regression/gates relevantes siguen verdes.

Documenta counts reales, skips opt-in y motivo de cualquier skip.

### 2. Contratos/canonical payload

Demostrar:

- `record_patch` es bounded/versionado;
- canonical serialization/fingerprint estable;
- tampering de target/field/value/context cambia/rechaza fingerprint;
- `ProposedAction` no concede autoridad;
- payload extras/coerciones ambiguas se rechazan.

### 3. Effective write schema + policy

Demostrar:

- write eligibility depende del usuario/contexto real;
- fields sensibles/no soportados no aparecen o no son elegibles;
- ActionPolicy conserva deny-by-default donde corresponda;
- schema/policy revision se liga al proposal/commit;
- no se amplía M5 QUERY.

### 4. Preview

Demostrar:

- preview no ejecuta write ni side effects;
- before/after provienen del estado real releído;
- ACL/record rules/field access/multi-company se respetan;
- precondition cambia cuando cambia el estado relevante;
- Evidence de preview es checked/bounded/sanitizada.

### 5. Approval

Demostrar:

- proposal/preview se persisten de forma durable;
- actor/database/company/target/payload/policy/precondition/expiry están ligados;
- approve/reject/expire/concurrency/replay se comportan según state machine;
- browser no puede sustituir el payload;
- no se almacenan secrets/tokens completos.

### 6. ACTION authority y commit

Demostrar:

- authority write está separada de M2/q1;
- sólo se emite después de approval válida;
- TTL/bindings/replay protection funcionan;
- Odoo revalida permisos/policy/precondition con `su=False` justo antes del write;
- el commit modifica sólo un record y fields aprobados;
- stale, field extra, x2many command, model/id/company tampering fallan antes de mutar;
- no existe generic method/action/write endpoint controlable por Codex.

### 7. Verification + audit

Demostrar:

- success sólo se declara tras reread coincidente;
- verification Evidence refleja after-state real;
- timeout/resultado ambiguo no provoca retry ciego;
- state `execution_unknown`/unverified se representa sin falso success;
- audit reconstruye proposal → approval → attempt → verification;
- audit no contiene shared secrets, action tokens, DSNs ni raw tracebacks.

### 8. ReasoningEngine / tools

Demostrar:

- ACTION tiene registry separada;
- Codex puede usar schema + preview;
- default ToolExecutor sigue read-only;
- EXPLAIN/QUERY/HOW_TO no reciben preview/write risks;
- Codex no dispone de `WRITE`/`ACTION`/commit tool;
- proposed_action inventada, proposal id de otro turn o fingerprint falso se rechazan;
- approve/execute determinista no vuelve a preguntar al LLM qué payload ejecutar.

### 9. Browser/UI/security

Con Chromium real demostrar:

- usuario ve target y diff exactos antes de aprobar;
- approval requiere acción explícita;
- cancel/reject no escribe;
- doble submit no duplica write;
- stale obliga a nueva preview;
- XSS payloads quedan escapados;
- no secrets en DOM/console/responses;
- browser sólo comunica con Odoo.

### 10. E2E real Codex ACTION

Ejecutar al menos:

1. happy path usuario A: petición natural → Codex → preview → click approve → commit → verification → record cambiado;
2. sin approval: no write;
3. usuario B/record rule denied: no write/no leak;
4. stale preview: no write;
5. tampering/replay/expiry: no write;
6. prompt injection/tool escalation: no authority escalation;
7. resultado de red ambiguo: verification antes de cualquier retry.

Registrar número de writes esperado/observado y comandos reproducibles.

Si Codex real no está disponible por auth/runtime externo, el gate **no puede declararse PASS pleno** sólo con fake engine. Debe marcarse `CONDITIONAL`/pendiente de verificación real, salvo que el Source of Truth defina otra semántica explícita.

### 11. Scope containment

Confirmar que M6 no ha introducido accidentalmente:

- create/delete genérico;
- multi-record/bulk write;
- shell/SQL/Python arbitrario;
- generic `execute_method`/`execute_kw`;
- autonomous approval;
- autonomous commit tool;
- business actions no allowlisted;
- policy/settings admin completas de M7;
- code paths específicos de Odoo 19/M8 en `application`.

## Gate report

Crear/actualizar `docs/M6_GATE_REPORT.md` con tabla al menos para:

- quality/lint/mypy;
- migrations/addon;
- M1-M5 regressions;
- contracts/canonicalization;
- effective write schema/policy;
- preview/no-side-effects;
- approval/state machine;
- action authority/commit;
- verification/audit;
- Codex ACTION tools;
- browser/security;
- real ACTION E2E;
- scope containment.

Incluir versión Odoo/Codex/runtime relevante, comandos, counts y cualquier limitación real.

## Veredicto

Usa semántica explícita:

- `PASS`: todos los checks obligatorios disponibles, incluido E2E real requerido, están verdes;
- `CONDITIONAL`: implementación determinista verde pero falta una verificación externa obligatoria no disponible en el host;
- `FAIL`: existe un fallo funcional/security/regresión o requirement sin implementar.

No usar `PASS` si:

- el write ocurre antes de approval;
- Codex tiene commit authority/tool;
- stale/replay/tampering puede escribir;
- success no está verificado por reread;
- browser puede sustituir el payload;
- faltan ACL/record-rule tests reales;
- M1-M5 regresan.

## Acceptance criteria

- `docs/M6_GATE_REPORT.md` contiene evidencia reproducible y veredicto inequívoco;
- M6 sólo se marca completado en roadmap/README si el gate es PASS;
- no se avanza a M7 dentro de esta task;
- cualquier deuda aceptada está descrita sin rebajar una invariante de seguridad.

## Después

1. Si PASS, actualizar estado documental de M6 sin iniciar M7.
2. Si CONDITIONAL/FAIL, mantener M6 abierto y listar exactamente qué falta.
3. No redactar ni implementar M7 salvo instrucción explícita posterior.

# M6 — ACTION segura

Estado: **M6-01..M6-10 implementados; milestone abierto porque M6 GATE está en FAIL.** La suite determinista está verde, pero falta el E2E externo real y existe una desviación no resuelta entre el alcance `record_patch` de estos packets y el requisito create/business-action del Source of Truth. Ver [`docs/M6_GATE_REPORT.md`](../../../M6_GATE_REPORT.md).

M6 empieza únicamente después de **M5 GATE: PASS**. Su objetivo es permitir que el usuario solicite desde el chat un cambio simple y acotado, vea exactamente qué se va a modificar, lo apruebe explícitamente y obtenga después una verificación y auditoría del resultado real.

Fuente de verdad: `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT_CONFIG.md`, `AGENTS.md`, `service/AGENTS.md`, `addons/AGENTS.md`, `tests/AGENTS.md` y el estado real dejado por M0-M5. Antes de implementar cada packet debe contrastarse de nuevo con el Source of Truth.

## Resultado observable

Primer vertical slice objetivo:

```text
usuario pide cambiar un campo simple de un registro
    ↓
Odoo deriva identidad y contexto real
    ↓
Assistant/Codex razonan con tools de lectura + preview explícita
    ↓
Odoo valida write access + policy sin escribir
    ↓
se crea proposal canónica + preview ligada al estado actual
    ↓
panel muestra target, before/after, warnings y expiración
    ↓
usuario aprueba explícitamente desde Odoo
    ↓
se deriva autoridad ACTION nueva, estrecha y de un solo uso
    ↓
Odoo revalida ACL/rules/policy/precondition y ejecuta ORM write
    ↓
Assistant relee el resultado como el mismo usuario
    ↓
verification Evidence + audit/receipt persistidos
    ↓
panel informa commit verificado o estado no confirmado
```

M6 implementa primero una **modificación de campos simple y policy-controlled**. No convierte el agente en una interfaz genérica a `write()`, métodos de modelo o acciones arbitrarias.

## Orden de ejecución

1. [`M6-01-action-contracts-policy.md`](M6-01-action-contracts-policy.md) — contratos ACTION, payload canónico y policy base.
2. [`M6-02-effective-write-schema.md`](M6-02-effective-write-schema.md) — schema efectivo de escritura y validación de cambios soportados.
3. [`M6-03-preview-pipeline.md`](M6-03-preview-pipeline.md) — preview real bajo usuario, diff y precondition fingerprint sin mutar Odoo.
4. [`M6-04-approval-persistence.md`](M6-04-approval-persistence.md) — persistencia, binding, expiración y state machine de approvals.
5. [`M6-05-action-authority-commit.md`](M6-05-action-authority-commit.md) — autoridad ACTION separada y commit ORM estrecho.
6. [`M6-06-verification-audit.md`](M6-06-verification-audit.md) — relectura, verification receipt y auditoría.
7. [`M6-07-action-workflow-tools.md`](M6-07-action-workflow-tools.md) — workflow ACTION con Codex y tool de preview, nunca commit autónomo.
8. [`M6-08-panel-approval-security.md`](M6-08-panel-approval-security.md) — UX de preview/approve/cancel y hardening del boundary browser→Odoo.
9. [`M6-09-real-e2e-action.md`](M6-09-real-e2e-action.md) — E2E real con Codex/Odoo/Chromium y casos adversariales.
10. [`M6-10-gate.md`](M6-10-gate.md) — gate integral y cierre de M6.

Cada packet sigue siendo una task independiente y debe poder verificarse antes de avanzar.

## Agrupación recomendada para Goal Mode

Para ahorrar contexto/tokens sin convertir M6 en una sola tarea gigante, ejecutar los packets **secuencialmente dentro de estos Goals**:

### Goal A — contrato, policy y preview

Ejecutar juntos: **M6-01 + M6-02 + M6-03**.

Son una sola cadena conceptual: definir qué es una acción válida → descubrir qué puede escribirse realmente → construir un preview verificable sin escribir. Completar y testear cada packet antes de pasar al siguiente dentro del mismo Goal.

### Goal B — approval, commit y verificación

Ejecutar juntos: **M6-04 + M6-05 + M6-06**.

Forman el boundary transaccional: approval persistida → autoridad de ejecución → ORM write → relectura/audit. No empezar M6-05 si la state machine/atomicidad de M6-04 no está verde.

### Goal C — agente y UX

Ejecutar juntos: **M6-07 + M6-08**.

Conectan el workflow ACTION al pipeline ya seguro y exponen la aprobación en el panel. El modelo sólo puede solicitar preview; la aprobación y ejecución siguen siendo host-controlled.

### Goal D — E2E y gate

Ejecutar juntos: **M6-09 + M6-10**.

Primero demostrar el flujo completo real y los fallos seguros; después ejecutar el gate. M6-10 no debe relajar tests para declarar PASS.

Prompt base recomendado para cada Goal:

```text
Implement the listed M6 task packets sequentially.
Treat each packet as an independent acceptance contract.
Complete and verify one packet before continuing to the next.
Run its mandatory tests after each packet and the combined regression suite at the end.
Do not weaken an earlier security invariant to make a later packet easier.
If an earlier assumption proves wrong, fix it before continuing.
Do not implement tasks outside this Goal.
```

## Invariantes de M6

- Mantener el flujo obligatorio `proposal → preview → approval → commit → verification`.
- `ProposedAction` y cualquier texto de Codex son **presentation/intention data**, nunca autoridad de escritura.
- El ReasoningEngine puede solicitar una preview acotada; **no recibe un tool de commit** en M6.
- El browser nunca envía un payload de write autoritativo. Como máximo identifica una proposal y una decisión; Odoo deriva identidad server-side y el host usa el payload canónico persistido.
- La approval se liga al payload canónico/fingerprint, database, uid, compañías, policy revision, target, precondition y expiración.
- Una approval no puede reutilizarse para otro target, payload, usuario, compañía o turn.
- M2 delegation y M5 `q1` QUERY authority no se reutilizan ni reinterpretan como write authority.
- Cualquier autoridad ACTION nueva debe ser explícita, corta, bounded, replay-protected y emitida sólo tras aprobación válida.
- Antes del commit se revalidan ACL, record rules, field access, policy y precondition bajo el usuario real; no `sudo()`.
- El commit inicial es una operación estrecha de record patch. No aceptar `write(values)` libre desde el modelo, relational command lists, context arbitrario, nombres de métodos o acciones server-side.
- Business actions futuras requieren handlers explícitamente allowlisted e idempotency/side-effect semantics propias; M6 no introduce un `execute_method` genérico.
- El Assistant Service no recibe credenciales SQL de Odoo ni modifica la DB Odoo directamente.
- El estado aprobado debe persistirse en la Assistant DB; secrets/tokens completos no forman parte del audit log ni de prompts.
- Si el registro cambia de forma relevante entre preview y commit, el write falla cerrado como stale y exige nueva preview/approval.
- Tras un commit aparentemente correcto se relee el resultado bajo el mismo usuario. No afirmar éxito si la verificación no confirma el estado esperado.
- Ante resultado de red ambiguo no repetir ciegamente una operación con side effects. El primer vertical slice debe ser idempotente por diseño o pasar a un estado explícito `execution_unknown` hasta verificar.
- Los datos escritos siguen siendo contenido no confiable frente a prompt injection cuando se recuperen en turns futuros.
- El browser continúa hablando únicamente con Odoo.
- EXPLAIN, QUERY y HOW_TO deben seguir funcionando sin ampliar sus registries ni risks.
- No introducir Settings/overrides de producto propios de M7 ni compatibilidad Odoo 19 de M8 salvo soporte mínimo imprescindible compartido.

## Decisión de alcance para el primer ACTION

El primer slice debe soportar un `record_patch` pequeño, tipado y bounded sobre fields permitidos por schema efectivo + policy. Priorizar tipos escalares sencillos. No soportar de inicio:

- `one2many` / `many2many` command lists;
- binary/upload;
- HTML sin una política explícita de sanitización;
- fields técnicos o de seguridad sensibles;
- creación/borrado de registros;
- llamadas a métodos de modelo;
- acciones de servidor;
- cambios masivos/multi-record;
- encadenamiento de varios commits en una sola approval.

Si el estado real del Source of Truth exige un primer business action concreto distinto de `record_patch`, documentar el conflicto antes de editar y adaptar el packet mediante ADR/actualización explícita, no mediante ampliación silenciosa.

## Gate de M6

M6 sólo se considera terminado cuando, como mínimo:

- una solicitud ACTION produce un payload canónico validado y una preview sin mutar datos;
- la preview refleja estado actual real bajo el usuario efectivo y está ligada a una precondition comprobable;
- el usuario ve el cambio exacto y debe aprobarlo explícitamente;
- aprobación, payload, actor, target, policy y expiración están ligados y persistidos;
- replay, tampering, approval cruzada, expiración y stale state fallan cerrado;
- el commit usa ORM bajo el usuario real y sólo fields/operación allowlisted;
- no existe commit tool disponible para Codex ni método Odoo genérico controlado por el modelo;
- el resultado se relee y se genera verification Evidence/receipt;
- el audit permite reconstruir proposal → approval → attempt → verification sin almacenar secretos;
- cancel/reject no escribe nada;
- ACL/record rules/field restrictions/multi-company se conservan en E2E real;
- existe al menos un E2E real con Codex + Odoo 18 + Chromium donde el usuario aprueba y el cambio queda verificado;
- M1-M5, suite, Ruff, mypy, migraciones y addon tests siguen verdes;
- no se han implementado capacidades de M7/M8 fuera de scope.

Un fake ReasoningEngine es válido para tests deterministas, pero no basta para cerrar el gate si el host de gate dispone del runtime Codex real requerido.

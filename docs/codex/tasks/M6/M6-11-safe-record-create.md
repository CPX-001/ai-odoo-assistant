# M6-11 — Safe record create

Estado: **implementada y verificada** (2026-08-23). M6-12 y el gate M6-13
también están completados con PASS.

## Contexto

- Requiere M6-01..M6-10 implementados y el estado técnico descrito en `docs/M6_GATE_REPORT.md`.
- El gate actual sólo permanece en FAIL porque el Source of Truth exige `create/update` seguro y al menos una business action curada; `record_patch` ya cubre update.
- Esta task debe cerrar exclusivamente la mitad `create` reutilizando el boundary ACTION existente. No debe reabrir ni simplificar la seguridad ya verificada para update.
- Antes de editar, relee el Source of Truth, `docs/ARCHITECTURE.md`, `docs/M6_ACTION_FOUNDATION.md`, `docs/codex/M6_ACTION_WORKFLOW.md`, los contratos M6 y el gate real.

## Objetivo

Añadir una operación `record_create` genérica pero estrecha, tipada y policy-controlled que permita proponer, previsualizar, aprobar, crear mediante ORM bajo el usuario efectivo y verificar un único registro sin exponer `create(values)` libre al ReasoningEngine ni al browser.

El flujo obligatorio sigue siendo:

```text
proposal → preview → approval → commit → verification
```

## Contratos que NO puedes romper

- `ProposedAction` continúa siendo intención/presentación, no autoridad.
- Codex no recibe tool de approval ni commit.
- Browser sólo habla con Odoo y nunca aporta identidad ni payload de create autoritativo.
- M2/v1, QUERY/q1 y ACTION preview/commit authorities existentes conservan compatibilidad y semántica.
- Odoo sigue siendo autoridad de ACL, record rules, field access, companies y business rules.
- Assistant Service no recibe credenciales SQL de Odoo ni escribe su DB directamente.
- No `sudo()`, SQL directo, shell/Python arbitrario, `execute_kw`, `execute_method`, method names controlados por el modelo ni context arbitrario.
- EXPLAIN/QUERY/HOW_TO y `record_patch` no deben ampliar registries ni risks.

## Debes reutilizar

- `ActionPolicy` y su revision/fingerprint.
- effective write schema M6 y validación runtime bajo usuario real.
- canonical payload/fingerprint y contracts strict/`extra="forbid"`.
- proposal/approval persistence y state machine.
- action authority one-shot y replay protection.
- verification Evidence, execution receipt y audit chain.
- browser approval UX existente cuando sea compatible.
- ToolExecutor/registry ACTION actual, sin convertirlo en executor genérico de writes.

No crear una segunda arquitectura paralela de approvals o execution.

## Debes implementar

### 1. Contrato `record_create`

Define un payload versionado y canónico con, como mínimo:

- operation/type = `record_create`;
- target model;
- conjunto pequeño y bounded de valores iniciales;
- effective create-schema revision;
- action-policy revision;
- actor/database/company bindings derivados server-side;
- canonical fingerprint estable.

Requisitos:

- un solo registro por proposal/approval;
- máximo explícito de fields y bytes;
- inputs strict, `extra="forbid"`, sin coerciones ambiguas;
- values sólo de fields declarados create-eligible por schema + policy;
- no aceptar record id aportado por el modelo/browser;
- no aceptar context, method, domain, defaults ejecutables ni expresiones.

### 2. Effective create schema

Extiende/reutiliza el schema de escritura para distinguir claramente `create` de `write`.

Debe calcularse bajo el usuario efectivo y expresar únicamente fields/tipos que el producto soporta para create. Como baseline seguro:

- scalar simples;
- `many2one` únicamente si el valor es un ID positivo y la policy lo permite;
- selection validada contra opciones efectivas;
- fechas/datetime/numéricos/boolean/string con validación tipada;
- required/default/readonly/compute relevantes para explicar el preview cuando puedan obtenerse de forma segura.

Bloquea inicialmente salvo evidencia/ADR explícito:

- `one2many`/`many2many` command lists;
- binary/upload;
- HTML sin política específica;
- fields técnicos, identidad, permisos, secrets o seguridad;
- modelos denylisted/sensibles;
- valores o defaults que requieran ejecutar código suministrado por el modelo.

No hardcodear clases por versión de Odoo.

### 3. Preview sin create

La preview **no puede crear ni hacer rollback de un create real como mecanismo normal de preview**.

Debe mostrar de forma citable y sanitizada:

- modelo objetivo;
- valores explícitos que se intentarán crear;
- labels/tipos relevantes del schema;
- warnings sobre defaults/computed values que sólo podrán verificarse después del create;
- policy/schema revisions y expiry;
- una precondition apropiada para create, al menos ligada a schema/policy/actor/company y cualquier referencia dependiente que deba seguir siendo válida.

Si un `many2one` u otra referencia permitida se usa en el payload, valida existencia/acceso bajo el usuario real antes de aprobar y vuelve a validarlo justo antes del commit.

No prometas before/after exacto para defaults server-side todavía no materializados; diferencia claramente `requested values` de `verified result`.

### 4. Approval y autoridad

La approval debe quedar ligada al payload canónico completo, actor, database, companies, policy/schema revisions, expiry y preconditions.

La autoridad de commit:

- es distinta de preview/read/query authorities;
- sólo se emite tras approval válida;
- es corta, bounded, replay-protected y específica de `record_create`;
- no autoriza otro model/payload/operation;
- no puede convertirse en un `create(values)` genérico reutilizable.

### 5. Commit ORM seguro

Implementa un handler interno estrecho para `record_create`:

- revalida authority + approval + policy + effective create schema + company + referencias inmediatamente antes de crear;
- ejecuta ORM como usuario real y `su=False`;
- crea exactamente un registro;
- response bounded y sanitizada;
- no acepta method names/context/extra values del caller;
- errores Odoo se reducen a códigos sanitizados.

### 6. Idempotencia / respuesta ambigua

Create no puede depender de “si no recibí respuesta, vuelvo a crear”. Debe existir una estrategia demostrablemente segura contra duplicados.

Preferencia arquitectónica: persistir en el boundary Odoo un execution/idempotency receipt ligado al `authority jti` + payload fingerprint en la misma transacción lógica que el create, de forma que una repetición tras respuesta perdida pueda devolver/reconciliar el resultado original sin ejecutar un segundo create.

Si el mecanismo actual de replay puede evolucionarse para guardar el resultado de `record_create`, reutilízalo. No introduzcas una dependencia de la Assistant DB para decidir si Odoo ya committed si esa DB no puede observar atómicamente el commit Odoo.

Documenta exactamente las garantías y cualquier límite. Si no puede demostrarse no-duplicación ante timeout post-commit, la task no está terminada.

### 7. Verification + Evidence + audit

Tras el commit:

- relee el registro creado como el mismo usuario;
- verifica que los values explícitamente aprobados coinciden con el estado observable;
- captura el nuevo record id sólo desde Odoo/receipt, nunca desde input del modelo;
- produce verification Evidence checked;
- persiste receipt/audit correlacionable proposal → approval → execution → verification;
- si no puede verificarse, usa estado explícito `execution_unknown`/`unverified`, nunca falso success.

Audit no debe contener secrets, full authority tokens, DSNs ni tracebacks crudos.

### 8. ReasoningEngine / tools

Codex puede recibir una tool host-controlled de **preview create**, si el workflow la necesita, construida desde schema/policy actuales.

No recibe:

- tool de commit;
- approval tool;
- raw `create`;
- generic write/action tool;
- model method executor.

El approve/execute posterior debe utilizar el proposal persistido, no volver a preguntarle al LLM qué crear.

## Fuera de scope

- bulk create;
- create de múltiples modelos en una approval;
- relational command lists;
- attachments/binary;
- delete/unlink;
- autonomous approval;
- business actions (M6-12);
- Settings/product hardening de M7;
- Odoo 19/M8.

## Tests obligatorios

### Contracts/policy

- canonicalization/fingerprint estable;
- extra keys/coerciones ambiguas rechazadas;
- model/field/type no elegible rechazado;
- policy/schema revision tampering rechazado;
- field/bytes caps.

### Odoo permissions

- create permitido funciona bajo usuario real;
- no create ACL falla cerrado;
- company/reference no permitida falla sin leak;
- field no create-eligible falla antes de ORM;
- sensitive model/field bloqueado por policy.

### Approval/security

- sin approval => cero create;
- reject/expired/cross-user/cross-company/tampered proposal => cero create;
- replay no crea dos registros;
- stale schema/policy/reference exige nueva preview/approval cuando corresponda;
- browser no puede sustituir model/values.

### Ambiguous network

Test real o integración equivalente que:

1. permita que Odoo haga commit del create;
2. pierda/corte la respuesta;
3. haga recovery/retry;
4. demuestre exactamente **un** registro creado;
5. recupere/verifique el record id original.

### Regressions

- `record_patch` M6 existente sigue verde;
- ACTION registry no expone commit;
- EXPLAIN/QUERY/HOW_TO sin cambios de authority;
- suite, Ruff, mypy, migrations/addon tests.

## Acceptance criteria

- el producto soporta create seguro de un único registro además de update;
- `record_create` usa el mismo pipeline M6 sin atajos de approval;
- no existe create genérico controlable por Codex/browser;
- ACL/record rules/company/field policy se respetan bajo usuario real;
- timeout post-commit no puede duplicar el registro;
- success sólo se declara tras verification;
- tests y regresiones verdes.

## Después

1. Documenta la semántica final de `record_create`, especialmente idempotencia y recovery.
2. M6-12 y M6-13 se ejecutaron después; el gate integral final es PASS.
3. No avances a M7.

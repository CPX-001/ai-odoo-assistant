# M6-12 — Curated business action

## Contexto

- Requiere M6-11 verde.
- El Source of Truth exige al menos una business action curada además de create/update seguro.
- M6 ya dispone de proposal/preview/approval/authority/verification/audit para `record_patch`; M6-11 añade `record_create`.
- Esta task debe demostrar el patrón correcto para **una acción de negocio explícita**, sin introducir un executor genérico de métodos Odoo.

## Objetivo

Implementar una business action real de Odoo mediante un handler explícitamente allowlisted, con preview verificable, approval ligada al payload, autoridad one-shot, ejecución bajo el usuario real, semántica de idempotencia definida y verification/audit posterior.

La acción inicial recomendada es **confirmar un `sale.order`** mediante un handler dedicado equivalente a `sale.order.confirm.v1`, porque:

- es una acción de negocio real y observable;
- ya existe contexto/source/E2E previo alrededor de `sale.order` en el repo;
- obliga a demostrar correctamente que una business action no es un simple field patch.

Antes de fijarla definitivamente, inspecciona el Source of Truth y el estado real del fixture/dependencias. Si éste exige explícitamente otra acción, usa esa. Si `sale.order` no puede probarse de forma reproducible en el host M6, documenta el conflicto antes de sustituirla por otra acción real de producto. **Un método inventado sólo en un fixture de tests no basta para cerrar el requirement de business action del producto.**

## Contratos que NO puedes romper

- nada de `execute_method`, `execute_kw`, `getattr(model, name)` ni method name recibido desde Codex/browser;
- el handler y su model/action son código/configuración host-controlled y explícitos;
- Codex no recibe tool de commit/execute;
- approval explícita obligatoria antes de cualquier side effect;
- Odoo ejecuta como usuario efectivo, `su=False`, conservando ACL/record rules/company/business rules;
- browser sólo comunica con Odoo y nunca envía authority/payload ejecutable;
- Assistant Service no usa SQL contra Odoo;
- una business action no puede reutilizar authority de `record_patch`, `record_create`, M2 o q1 sin un contrato explícito compatible.

## Debes reutilizar

- ActionPolicy y revisions;
- proposal/approval repository/state machine;
- canonical fingerprints y actor/company/database bindings;
- authority one-shot/replay protections;
- verification/audit pipeline;
- Odoo internal machine-auth boundary;
- ACTION workflow y panel existentes;
- Evidence ledger/AnswerEnvelope;
- patrones de respuesta ambigua ya probados en M6.

## Debes implementar

### 1. Catálogo/registro de business actions explícitas

Introduce el mínimo mecanismo necesario para registrar handlers curados sin crear un framework universal.

Cada action spec debe estar definido por el host y declarar al menos:

- stable action id/version, por ejemplo `sale.order.confirm.v1`;
- model exacto;
- operación/handler concreto;
- requirements de estado/preconditions;
- risk/approval requirement;
- campos mínimos necesarios para preview/verification;
- política de idempotencia/retry;
- límites y outcome esperado verificable.

No permitir que model/method/action id arbitrarios lleguen a resolución dinámica.

Si existe un registry, debe ser explícito e inmutable por turn; nada de discovery/reflection automática.

### 2. Payload canónico

Define payload versionado para curated action con únicamente datos necesarios, por ejemplo:

- action id exacto allowlisted;
- target model/id;
- parámetros tipados **sólo si esa acción concreta los necesita**;
- policy/action-spec revision;
- precondition fingerprint;
- actor/database/company bindings derivados server-side.

Para confirmar `sale.order`, el payload inicial idealmente no necesita parámetros libres además del target.

Strict + `extra="forbid"`; no context arbitrario, method names, kwargs genéricos, domains ni expresiones.

### 3. Preview real

La preview debe releer el target bajo el usuario real y validar que la acción puede plantearse sin ejecutarla.

Para `sale.order.confirm.v1`, como mínimo:

- target visible y accesible;
- estado actual compatible con confirmación según policy/handler;
- identidad/display name citable;
- before-state relevante;
- resumen claro de la acción y warnings sobre side effects conocidos;
- precondition fingerprint que cambie si el estado relevante cambia;
- Evidence checked.

No ejecutar el método real dentro de savepoint/rollback como sustituto de una preview de producto si eso dispara hooks/side effects no controlables.

No prometas una enumeración perfecta de todos los side effects dinámicos de módulos instalados. Presenta el alcance conocido y una warning cuando extensiones puedan añadir efectos adicionales.

### 4. Approval

Persistir proposal/preview exactamente como el usuario lo ve y ligar approval a:

- action spec/version;
- target;
- actor/database/company;
- payload fingerprint;
- precondition;
- policy revision;
- expiry.

Cambiar target/action/params/state invalida la approval.

### 5. Authority y handler

La authority de business action:

- sólo se emite tras approval válida;
- está ligada al action id y target exactos;
- TTL corto + one-shot/replay protected;
- no autoriza otros handlers ni un método genérico.

El Odoo-side handler debe llamar **directamente** al método/action codificado para esa spec después de revalidar permisos, state, policy y precondition.

Para `sale.order.confirm.v1`, el código puede conocer `sale.order` y `action_confirm` dentro del adapter/handler específico; lo que está prohibido es convertir esos strings en input arbitrario del agente o en un endpoint genérico.

### 6. Semántica de idempotencia y side effects

Documenta y prueba la semántica real del handler.

Para una acción de confirmación:

- si el target ya está en el estado verificado de éxito por una ejecución anterior del mismo attempt, recovery debe verificar y devolver el resultado sin repetir side effects;
- si el estado cambió por otro actor antes del commit, falla `stale`/requiere nueva preview salvo que pueda demostrarse que el outcome aprobado ya se alcanzó por el mismo attempt;
- si la respuesta se pierde después del commit, no re-ejecutar ciegamente;
- usa execution receipt/idempotency marker del boundary Odoo cuando sea necesario para distinguir retry del mismo attempt de una acción externa.

No declares idempotente una acción sólo porque “normalmente llamar dos veces no hace nada”. Debe estar soportado por estado/receipt verificable.

### 7. Verification + audit

Después de ejecutar:

- relee target bajo el mismo usuario;
- valida outcome específico del handler;
- produce Evidence checked y receipt;
- audit correlaciona proposal → approval → action attempt → verification;
- no claim success si el outcome no está confirmado.

Para confirmación de pedido, verificar como mínimo que el pedido abandonó el estado pre-confirmación y quedó en un estado aceptado por la spec; si el repo/fixture permite validar un side effect determinista relevante sin acoplarse a módulos opcionales, inclúyelo.

### 8. ReasoningEngine y UI

Codex puede solicitar la preview de una curated action permitida por el registry ACTION del turn. El modelo no recibe execute.

La UI debe mostrar de forma inequívoca:

- acción concreta;
- registro target;
- estado actual;
- efecto principal esperado;
- warnings;
- approve/reject.

El click de approval sólo envía proposal id + decisión mínima y Odoo deriva actor server-side.

## Fuera de scope

- catálogo amplio de business actions;
- method/action discovery automático;
- arbitrary args/kwargs;
- multi-record actions;
- cron/background autonomous actions;
- create/delete/update adicional fuera del cierre M6;
- rollback automático de side effects;
- M7 Settings para administrar actions;
- Odoo 19.

## Tests obligatorios

### Registry/contract

- sólo action id allowlisted disponible;
- action/model/method inventados rechazados;
- extra params/context/kwargs rechazados;
- registry EXPLAIN/QUERY/HOW_TO no recibe ACTION handler.

### Preview/approval

- preview cero side effects;
- target no visible/ACL denied/record rule denied falla sin leak;
- invalid current state falla cerrado;
- stale state invalida approval;
- reject/expiry/cross-user/cross-company/tampering => cero action execution.

### Commit

- happy path ejecuta exactamente una vez;
- `su=False` y permisos reales preservados;
- replay/double click no repite efectos;
- response perdida post-commit se resuelve por verification/receipt sin segunda ejecución;
- arbitrary method injection imposible.

### Verification/audit

- success sólo con outcome verificado;
- execution_unknown/unverified cuando corresponde;
- receipt/audit sin secrets/tokens/tracebacks.

### Real Odoo

- al menos un test/E2E sobre la acción real escogida, no sólo mocks;
- si es `sale.order.confirm.v1`, crear fixture reproducible con un pedido confirmable y demostrar state transition bajo un usuario autorizado;
- usuario restringido no puede ejecutar ni inferir datos prohibidos.

### Regressions

- `record_patch` y `record_create` siguen verdes;
- M1-M5 regressions;
- suite, Ruff, mypy, migrations/addon.

## Acceptance criteria

- existe al menos una business action real y explícitamente curada en producto;
- no existe endpoint/tool genérico para ejecutar métodos;
- preview y approval preceden siempre al side effect;
- authority exacta, one-shot y replay-protected;
- permisos/state/precondition se revalidan justo antes de ejecutar;
- timeout/retry no duplica side effects;
- outcome se verifica y audita;
- acción real E2E verde.

## Después

1. Documenta la spec/handler y su semántica de idempotencia.
2. No marques todavía M6 PASS: **M6-13 debe repetir el gate completo contra el Source of Truth**.
3. No avances a M7.

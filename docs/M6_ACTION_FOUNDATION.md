# M6 ACTION transactional boundary — M6-01 a M6-13

Estado: **implementado, verificado y con M6 GATE: PASS.**

El flujo transaccional disponible es:

```text
proposal validada → schema efectivo → preview persistida → aprobación
→ commit único → relectura y verificación
```

## Payload y policy

El payload ACTION es una unión cerrada: `record_patch` actualiza un registro,
`record_create` solicita crear exactamente uno y `business_action` sólo admite
acciones curadas por ID estable. Patch/create admiten un máximo de cuatro
fields y ligan `instance_id`, database, uid, compañías, turn/proposal, target,
policy y schema. Los valores están etiquetados y son datos escalares; no
admiten métodos, context, domains, IDs de destino para create, defaults
ejecutables, Python, SQL ni command lists de Odoo.

La única canonicalización ordena compañías y cambios por field y serializa JSON
estricto UTF-8. Su identificador es
`action-payload:v1:sha256:<digest>`. Los decimales, fechas y datetimes tienen
representación canónica para evitar approvals ambiguas en packets posteriores.

La policy `m6-record-patch-v1` aplica límites de tamaño/fields y deniega models
y fields sensibles aunque Odoo conceda permisos. Esta policy complementa las
ACL y record rules; nunca las sustituye.

## Schema efectivo

La autoridad `p1` es distinta de las delegaciones de lectura `v1` y QUERY
`q1`. Es corta, de un solo uso por scope y queda ligada server-side a database,
uid, compañía activa, compañías permitidas, model, record, fields, turn y
policy. El handler usa un environment Odoo con `su=False`.

El schema efectivo queda ligado además a instance/database/user/companies y
sólo conserva fields no-readonly que pasen acceso de field y policy. Los tipos
admitidos son:

- boolean, char/text, integer;
- date y datetime UTC canónico;
- float/monetary como decimal canónico;
- selection con opciones runtime;
- many2one con relación explícita y comprobación de lectura del id objetivo.

Quedan pospuestos x2many, binary, HTML, reference/polymorphic, JSON, fields
técnicos/sensibles, delete y métodos de negocio.

El mismo documento de schema distingue `write_access/fields` de
`create_access/create_fields`. La capacidad create se calcula bajo el usuario
efectivo y aplica los mismos límites de tipos, field access y policy sin asumir
que todo field escribible sea automáticamente creable.

## Preview y precondition

`/odoo_ai/internal/v1/action-preview` acepta exclusivamente el proposal
canónico, su fingerprint y el turn. Después de verificar machine auth y `p1`,
Odoo vuelve a comprobar model/record/field access bajo el usuario real, relee
sólo los fields afectados y devuelve un diff before/after bounded.

La precondition es:

```text
action-precondition:v1:sha256(
  canonical_json({format_version, model, record_id, before[field...]})
)
```

Por tanto, cualquier cambio posterior en uno de los valores observados produce
otra precondition y deberá forzar nueva preview antes de un futuro commit. No
incluye fields ajenos al write set ni pretende detectar efectos externos no
observados.

La preview no llama `write()`, `onchange` ni métodos de negocio. Ejecutarlos
para “simular” produciría side effects o resultados incompletos difíciles de
representar con seguridad. La respuesta muestra una limitación host-controlled
y genera Evidence `RECORD` checked, pero no concede autoridad de escritura.

Para `record_create`, la preview tampoco llama `create()` ni simula mediante
rollback. Presenta únicamente los valores solicitados y avisa que defaults,
computados y efectos secundarios sólo se conocerán tras el commit. Las
referencias `many2one` se comprueban bajo el usuario real. Su precondition liga
payload, actor, compañías, revisiones y referencias validadas.

## Approval durable (M6-04)

El Assistant Service persiste el payload canónico exacto, fingerprint, preview,
precondition, actor y caducidad en su PostgreSQL separado. La decisión entrante
contiene sólo `proposal_id`, `approve|reject` y el contexto de actor derivado por
Odoo; values, target o payload alternativos son rechazados por contrato.

La fila se bloquea durante la decisión. Sólo `previewed` puede pasar una vez a
`approved` o `rejected`; concurrencia, replay, actor distinto y expiración
fallan cerrados. El approval aprobado devuelve un UUID opaco, no un payload
editable, y no existe write durante esta fase.

## Autoridad y commit (M6-05)

`a1` es una familia HMAC distinta de `v1`, `q1` y `p1`, con key purpose propio
y secret file configurable mediante `ODOO_AI_ACTION_AUTHORITY_SECRET_FILE`.
El Assistant Service sólo la emite después de cambiar atómicamente un approval
de `approved` a `executing`. Liga approval/proposal/attempt, instance/database,
usuario, compañías, model, record, fields, fingerprints, revisiones, scope y
caducidad.

`/odoo_ai/internal/v1/action-commit` acepta únicamente esa autoridad y el
proposal persistido. Odoo vuelve a validar policy, schema, ACL, field access,
record rules, compañías y precondition usando `api.Environment(..., su=False)`.
Construye server-side el diccionario de values y contiene exactamente una
llamada posible a `write()` sobre un registro. No acepta métodos, context,
domains, SQL, Python ni command lists. El `(jti, action_commit)` se consume en
el ledger antes del intento. Un timeout o respuesta ambigua nunca provoca un
retry del write.

## Verificación, Evidence y audit (M6-06)

Tras un commit confirmado, o para resolver un resultado ambiguo, el servicio
emite otro `a1` de un solo uso con scope `action_verify`. Odoo relee sólo los
fields afectados bajo el mismo usuario y normaliza los valores con el mismo
contrato que la preview. El estado es `verified` exclusivamente cuando el mapa
after coincide exactamente con el payload aprobado.

Un commit confirmado que no puede verificarse queda `committed_unverified`; un
commit ambiguo sin confirmación exacta permanece `execution_unknown`. Una
precondition distinta queda `stale`. La verificación exacta produce Evidence
`RECORD` checked y un receipt ligado a proposal/approval/attempt/fingerprint.
La Assistant DB conserva además eventos append-only sanitizados con IDs,
estado, revisiones y fingerprints; no guarda tokens de autoridad, secrets ni
prompts en el audit.

## Create seguro e idempotencia (M6-11)

Tras approval, `record_create` recibe scopes `action_create_commit` y
`action_create_verify`, distintos de patch, preview y query. Odoo revalida
policy, schema create, ACL, field access, compañías y referencias con
`su=False`, construye los values server-side y ejecuta como máximo un
`model.create(values)`.

Antes del efecto, Odoo reclama un receipt privado
`odoo.ai.action.execution` ligado a `attempt_id`, authority `jti`, proposal,
kind, payload fingerprint y model. El receipt y el registro creado se confirman
en la misma transacción PostgreSQL de Odoo. Si la respuesta se pierde, una
repetición del mismo intento devuelve el `target_record_id` ya persistido; no
vuelve a ejecutar `create`. Verification localiza ese receipt, relee el
registro original como el mismo usuario y sólo produce Evidence checked cuando
los valores explícitamente aprobados coinciden.

La garantía cubre retries o recovery del mismo `attempt_id`. Un intento nuevo
requiere una approval nueva y constituye una nueva acción de usuario. Los
receipts expirados se eliminan mediante autovacuum después de que haya vencido
su autoridad; la Assistant DB nunca decide si el commit Odoo ocurrió.

## Business action curada (M6-12)

La primera spec de producto es `sale.order.confirm.v1`: model exacto
`sale.order`, target de un solo registro y cero parámetros libres. La preview
relee `name` y `state` bajo el usuario real, sólo acepta `draft|sent`, muestra
el outcome esperado y liga una revisión de spec y una precondition al estado.
El addon declara `sale` como dependencia, de modo que la spec no se habilita
por accidente sólo porque otro módulo del deployment la haya instalado.

El commit usa un handler dedicado que llama directamente a
`records.action_confirm()`; no resuelve nombres con reflection ni acepta
method/context/kwargs desde Codex, browser o Assistant. Sus scopes
`business_action_commit` y `business_action_verify` son distintos de patch,
create, preview, QUERY y lectura. ACL, record rules, compañía, estado y
precondition se revalidan con `su=False` inmediatamente antes de la acción.

El receipt Odoo se reclama y completa en la misma transacción que la
confirmación. Una respuesta perdida se recupera por el mismo attempt sin
repetir `action_confirm`; verification relee el estado y sólo acepta
`sale|done`. Codex sigue sin recibir un tool de commit y el browser continúa
hablando sólo con Odoo.

El análisis previo del donor ERPipe y las razones para adoptar sólo conceptos
están en [`third_party/M6_ERPIPE_WRITE_AUDIT.md`](third_party/M6_ERPIPE_WRITE_AUDIT.md).

# M6 ACTION transactional boundary — M6-01 a M6-06

Estado: **implementado y verificado hasta M6-06.**

El flujo transaccional disponible es:

```text
proposal validada → schema efectivo → preview persistida → aprobación
→ commit único → relectura y verificación
```

## Payload y policy

`ActionProposalPayload` representa un único `record_patch` sobre un registro y
un máximo de cuatro fields. Liga `instance_id`, database, uid, compañías,
turn/proposal, target, policy y schema. Los valores están etiquetados y son
datos escalares; no admite métodos, context, domains, Python, SQL ni command
lists de Odoo.

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
técnicos/sensibles, create/delete y métodos de negocio.

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

## Deliberadamente pendiente

M6-07 y siguientes conectarán este boundary a handlers de negocio y a la UX
Odoo-native. Codex sigue sin recibir un tool de commit y el browser continúa
hablando sólo con Odoo.

El análisis previo del donor ERPipe y las razones para adoptar sólo conceptos
están en [`third_party/M6_ERPIPE_WRITE_AUDIT.md`](third_party/M6_ERPIPE_WRITE_AUDIT.md).

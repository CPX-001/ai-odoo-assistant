# M6 ACTION foundation — M6-01 a M6-03

Estado: **implementado y verificado; no existe capacidad de commit.**

Este documento fija la base entregada antes de persistir approvals o habilitar
escrituras. El flujo disponible termina en:

```text
proposal validada → schema efectivo de escritura → preview sin efectos
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

## Deliberadamente pendiente

M6-04 a M6-06 permanecen sin implementar: persistencia/state machine de
approval, autoridad separada de commit, ORM write, relectura, receipt y audit.
En consecuencia, esta base no permite modificar Odoo.

El análisis previo del donor ERPipe y las razones para adoptar sólo conceptos
están en [`third_party/M6_ERPIPE_WRITE_AUDIT.md`](third_party/M6_ERPIPE_WRITE_AUDIT.md).

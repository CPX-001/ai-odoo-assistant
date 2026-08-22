# Contrato QUERY seguro (M5-03)

QUERY usa estructuras JSON tipadas y acotadas. El modelo nunca entrega un domain
Odoo, una cadena `order`, SQL, contexto, código Python ni un nombre de método.
El Assistant valida primero contra `EffectiveModelSchema`; el addon vuelve a
validar contra la autoridad firmada y el schema/campo real antes de construir la
llamada ORM.

## Búsqueda y lectura

```json
{
  "model": "sale.order",
  "schema_id": "sha256:<schema efectivo>",
  "fields": ["name", "amount_total"],
  "filter": {
    "match": "all",
    "conditions": [
      {"field": "state", "operator": "eq", "value": "sale"}
    ]
  },
  "order": [{"field": "amount_total", "direction": "desc"}],
  "limit": 20
}
```

- `match`: `all` o `any`, sin anidamiento.
- operadores: `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `not_in` y
  `contains`; cada uno se allowlistea por tipo de campo.
- hasta 8 condiciones, 3 términos de orden, 16 campos y 50 registros.
- `in`/`not_in` admiten como máximo 32 valores escalares.
- `schema_id` vincula la petición al schema efectivo exacto del turno. No se
  transmite a Odoo como domain ni como contexto.

El addon traduce esta estructura a domain/order sólo tras comprobar modelo,
campo, tipo, `searchable`/`sortable`, acceso de campo y límites. `search()` y
`read()` se ejecutan con el usuario delegado, `su=False`, compañías activas y
record rules de Odoo.

## Agregación

```json
{
  "model": "sale.order",
  "schema_id": "sha256:<schema efectivo>",
  "filter": {"match": "all", "conditions": []},
  "metrics": [
    {"operation": "count", "field": null},
    {"operation": "sum", "field": "amount_total"}
  ],
  "group_by": ["state"],
  "group_limit": 20
}
```

- métricas: `count`; y `sum`, `min`, `max` sólo en tipos compatibles.
- hasta 8 métricas, 2 campos de agrupación y 50 grupos.
- el addon usa `read_group()` y devuelve sólo grupos/métricas normalizados,
  nunca `__domain` ni contexto interno.

Un resultado vacío sigue generando Evidence `checked`. Todas las respuestas
incluyen `captured_at`, counts, límite y `truncated`, y además están limitadas por
tamaño serializado.

## Autoridad y compatibilidad M2

M2 conserva sin cambios su token `v1`, ligado a IDs concretos y scopes
`fields_get`/`read_records`. QUERY usa una familia separada `q1`, derivada con un
purpose criptográfico distinto y ligada a:

- turno, base, usuario, compañía efectiva y compañías activas;
- un único modelo y la allowlist de campos visibles obtenida en runtime;
- scopes independientes `query_schema`, `query_records` y
  `aggregate_records`;
- expiración, revisión de policy y caps de records, fields, condiciones,
  métricas y grupos.

Cada scope se consume una vez mediante el ledger de replay. Un token `v1` no se
puede decodificar como `q1`, ni al contrario; por tanto M5 no amplía
implícitamente ninguna autoridad emitida para M2.

## Dynamic tools y workflow (M5-04)

El registry QUERY por turno contiene exactamente:

- `odoo.get_effective_schema` (`GetEffectiveSchemaRequest`): recibe sólo el
  modelo actual y devuelve `effective_schema`, `evidence_id` y estado.
- `odoo.query_records` (`QueryRecordsRequest`): recibe la AST de búsqueda
  documentada arriba y devuelve el resultado normalizado más su Evidence.
- `odoo.aggregate_records` (`AggregateRecordsRequest`): recibe la AST de
  agregación y devuelve grupos/métricas normalizados más su Evidence.

Los tres schemas Pydantic usan `extra="forbid"`. El host compara cada `ToolSpec`
con el catálogo canónico, vincula el backend a `uid` y modelo del turno, y aplica
los budgets agregados de `ToolExecutor`. QUERY no registra source tools, shell,
filesystem, red, apps ni tools genéricas.

Ejemplo abreviado de Evidence de records:

```json
{
  "kind": "record",
  "status": "checked",
  "pointer": {
    "provider": "odoo_query",
    "operation": "query_records",
    "model": "sale.order",
    "schema_id": "sha256:..."
  },
  "payload": {
    "returned_count": 2,
    "limit": 20,
    "truncated": false,
    "records": ["...bounded normalized rows..."]
  }
}
```

Ejemplo abreviado de aggregate vacío comprobado:

```json
{
  "kind": "record",
  "status": "checked",
  "pointer": {
    "provider": "odoo_query",
    "operation": "aggregate_records",
    "model": "sale.order",
    "schema_id": "sha256:..."
  },
  "payload": {
    "groups": [{"group": {}, "metrics": [{"operation": "count", "value": 0}]}],
    "returned_group_count": 1,
    "group_limit": 20,
    "truncated": false
  }
}
```

`QueryService` exige workflow `QUERY`, ausencia de `proposed_action`, Evidence
`checked` perteneciente al ledger y una cita QUERY renderizable. Si el resultado
está truncado, el `AnswerEnvelope` debe declarar esa limitación. Odoo devuelve al
browser sólo respuesta, confianza, limitaciones y pointers de cita; nunca filas,
tokens ni transcripts de tools. La ruta de producto es browser → Odoo
`/odoo_ai/v1/query` → Assistant `/v1/turns/query` → endpoints ORM internos.

# M5-03 — QUERY ORM segura y autoridad acotada

## Contexto

- Requiere M5-01 verde.
- M2 sólo autoriza `fields_get` y lectura exacta de record IDs. M5 **no puede ensanchar silenciosamente** ese token/format.
- El objetivo QUERY requiere búsqueda, filtros, orden y agregaciones bounded bajo ACL/record rules reales.

## Objetivo

Crear primitives ORM read-only para QUERY mediante estructuras tipadas validadas contra `EffectiveModelSchema`, con autoridad explícita por turn y sin aceptar domains/order/métodos arbitrarios del modelo.

## Antes de decidir implementación

Inspecciona el formato de delegación actual y el wiring real. Si QUERY necesita nuevos scopes, preserva compatibilidad M2 mediante una evolución explícita del contrato (por ejemplo versión nueva o autoridad QUERY separada). No reinterpretar un token M2 válido como autorización QUERY.

## Debes implementar

### Query contracts

Define una AST/estructura pequeña, no strings ejecutables, con capacidades equivalentes a:

- modelo objetivo;
- filtros simples combinados de forma explícita y bounded;
- operadores allowlisted apropiados al field type;
- selección de fields;
- sort field + dirección;
- limit con cap server-side;
- agregaciones allowlisted (`count` y sólo otras como `sum/min/max` cuando el tipo lo permita);
- group-by sólo en fields permitidos y con cardinalidad/result caps.

No aceptar domain Python/list crudo con operadores lógicos libres, `order` string libre, SQL, expresiones, nombres de métodos ni context arbitrario.

### Autoridad QUERY

- scopes/capabilities explícitas por turn;
- binding a database, uid, compañías, modelos permitidos, límites y expiración;
- replay protection al menos equivalente a M2;
- un scope no puede reutilizarse para otra operación o ampliar modelos/fields.

### Ejecución Odoo

Implementar endpoints/handlers internos estrechos para:

1. búsqueda + lectura bounded;
2. agregación bounded.

El host construye el domain/order real después de validar la estructura contra schema/policy. La ejecución debe usar ORM como usuario real, `su=False`, conservando ACL, record rules, field access y multi-company.

- parámetros siempre datos, nunca código;
- response bounded y normalizada;
- resultado vacío es válido y verificable;
- errores Odoo se reducen a códigos sanitizados;
- no generic `execute_method`/`execute_kw`.

### Evidence

Cada ejecución válida produce Evidence checked que describa de forma citable:

- modelo;
- query canónica sanitizada;
- records/resultados o agregados devueltos;
- `captured_at`;
- counts/limits necesarios para interpretar truncation.

No incluir token, DSN, endpoint interno ni domain Odoo crudo si puede exponer detalles innecesarios.

## Fuera de scope

- dynamic tools/Codex;
- HOW_TO;
- export masivo/paginación sin límite;
- joins SQL;
- writes/actions.

## Tests obligatorios

- filtro/sort permitido funciona;
- operator incompatible con field type se rechaza;
- field/model fuera de schema se rechaza antes de ejecutar;
- ACL/record rules ocultan registros no permitidos;
- field access denegado no se filtra;
- allowed companies se conservan;
- strings tipo SQL/injection se tratan sólo como valores;
- límites de records/groups/fields/bytes;
- empty result produce Evidence checked;
- replay y scope/model tampering fallan cerrado;
- M2 exact-read sigue compatible;
- suite, Ruff y mypy.

## Acceptance criteria

- QUERY dispone de primitives expresivas pero no de un lenguaje ejecutable arbitrario;
- toda operación se valida contra schema efectivo y autoridad server-side;
- Odoo sigue aplicando sus permisos reales;
- no existe acceso SQL del Assistant a Odoo ni métodos genéricos.

## Después

1. Documenta la gramática/AST final de filtros y agregaciones.
2. Explica cómo evolucionó la autoridad respecto a M2 sin ampliarla implícitamente.
3. No avances a M5-04.

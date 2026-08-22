# M5-01 — Effective runtime schema

## Contexto

- Requiere **M4 GATE: PASS**.
- `OdooGateway.get_model_metadata()` ya obtiene metadata bajo delegación, pero M5 necesita una representación explícita que gobierne exposición y validación de futuras queries.
- `docs/ARCHITECTURE.md` fija que sólo el schema efectivo runtime debe gobernar fields durante un turn.

## Objetivo

Introducir un `EffectiveModelSchema` pequeño y provider-neutral, derivado de Odoo bajo el usuario efectivo, que describa exactamente qué modelo/campos/operaciones de lectura puede usar M5 durante un turn.

## Contratos que NO puedes romper

- `service/src/odoo_ai/ports/odoo.py` no se convierte en un RPC genérico.
- `application` no importa Odoo ni adapters concretos.
- no clases/modelos por versión Odoo.
- identidad, compañías y permisos siguen siendo autoritativos en Odoo.

## Debes implementar

- contratos tipados para schema efectivo de modelo y fields;
- al menos: nombre técnico, label opcional, field type, relation, required/readonly/searchable/sortable/groupable según capacidades realmente demostrables;
- normalización determinista de selection/relation metadata;
- caps de número de fields y bytes;
- función/application service que obtenga metadata mediante el gateway y produzca schema efectivo;
- rechazo fail-closed de metadata inconsistente, duplicada o no soportada;
- Evidence `METADATA` checked asociada al schema usado;
- export JSON Schema de los nuevos contratos públicos si son públicos.

No inventar `searchable=True` para tipos/fields que no hayan sido validados como utilizables por el backend elegido.

## Fuera de scope

- ejecutar queries;
- navegación/menús;
- RAG documental;
- writes;
- caché global compleja de schemas.

## Tests obligatorios

- field permitido aparece en schema efectivo;
- field no visible/no devuelto por Odoo no aparece;
- relation/selection bounded;
- metadata malformada falla cerrado;
- caps de fields/bytes;
- no version checks ni imports Odoo en `application`;
- JSON Schema reproducible si aplica;
- suite, Ruff y mypy.

## Acceptance criteria

- existe una única representación efectiva que pueda gobernar las queries de M5;
- el schema procede de Odoo bajo identidad real y no de listas hardcodeadas;
- sus límites y Evidence son deterministas;
- todavía no existe ejecución QUERY.

## Después

1. Muestra un schema efectivo de ejemplo sanitizado.
2. Explica qué propiedades son hechos de Odoo y cuáles policy derivada.
3. No avances a M5-02.

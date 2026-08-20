# M1-03 — Persistencia mínima de runtime

## Contexto

- Requiere M1-02 completado y verde.
- El Source of Truth fija como tablas mínimas de M1: `instance_profile`, `capability_snapshot`, `trace_event`.

## Objetivo

Persistir los hechos mínimos necesarios para describir la instancia/runtime y observar eventos técnicos sin introducir todavía conversaciones, RAG, scanner, approvals ni datos vivos de negocio Odoo.

## Contratos que NO puedes romper

- contratos/ports de M0;
- storage y migraciones de M1-02;
- separación DB Assistant / DB Odoo.

## Debes implementar

- modelos SQLAlchemy y migración Alembic para:
  - `instance_profile`;
  - `capability_snapshot`;
  - `trace_event`;
- columnas mínimas justificadas por responsabilidades del Source of Truth;
- timestamps y claves/índices sólo donde sean necesarios;
- funciones/repositorios concretos mínimos para crear/leer esos registros si la siguiente task los necesita;
- tests de persistencia y migración.

No congeles APIs de dominio innecesarias. Si el Source of Truth no fija un campo exacto, elige la representación mínima y documenta brevemente la decisión.

## Fuera de scope

- conversación/mensajes/turns completos;
- source index;
- logs del host;
- knowledge/RAG;
- approvals/actions;
- datos de registros Odoo;
- event bus o observabilidad compleja.

## Restricciones

- no guardar passwords, API keys, shared secrets ni raw config sensible;
- `trace_event` debe almacenar metadatos/eventos técnicos sanitizados, no prompts completos por defecto;
- evitar JSON blobs como sustituto de un modelo cuando haya campos claramente estructurales, pero no sobre-modelar datos aún inexistentes.

## Tests obligatorios

- upgrade desde DB vacía hasta `head`;
- CRUD mínimo necesario de las tres tablas;
- constraints/índices relevantes;
- suite completa, lint y type-check.

## Acceptance criteria

- las tres tablas existen tras `alembic upgrade head`;
- se pueden escribir/leer datos de ejemplo sin secretos;
- una DB nueva y una DB de M1-02 migran correctamente;
- no se ha añadido persistencia de features posteriores;
- tests verdes.

## Antes de editar

1. Inspecciona modelos/migrations reales.
2. Resume el schema mínimo propuesto antes de implementarlo.
3. Señala cualquier campo que sea inferencia y no decisión explícita del Source of Truth.

## Después

1. Ejecuta migraciones/tests.
2. Resume schema final y decisiones.
3. No avances a M1-04.

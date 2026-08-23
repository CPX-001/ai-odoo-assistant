# M6-04 — Persistencia y state machine de approvals

Estado: **implementado y verificado de forma determinista el 2026-08-23.**

## Contexto

- Requiere M6-01..M6-03 verdes.
- La arquitectura asigna approvals al boundary Odoo + Assistant y reserva la Assistant DB para approvals/audit.
- Una preview válida sigue sin ser autorización de escritura.

## Objetivo

Persistir proposals/previews y decisiones de usuario mediante una state machine explícita que ligue aprobación a payload, actor, target, contexto, expiración y precondition, con transiciones atómicas y sin ejecutar todavía ningún write.

## Contratos que NO puedes romper

- El browser no aporta identidad confiable ni payload autoritativo.
- La approval debe referenciar el payload canónico persistido; no reconstruirse desde texto del modelo o datos editables del cliente.
- No reutilizar M2/q1 tokens como approval.

## Debes reutilizar

- Assistant PostgreSQL + sistema de migraciones actual;
- IDs/turn correlation existentes;
- canonical fingerprint de M6-01;
- preview/precondition de M6-03;
- patrones de persistencia transaccional/replay si ya existen.

## Debes implementar

### Persistencia

Añade las tablas/modelos mínimos necesarios para conservar, al menos:

- proposal id y format version;
- turn/workflow;
- database/instance binding;
- uid y contexto de compañías relevante;
- target model + record id;
- canonical payload + payload fingerprint;
- policy/schema revision;
- preview summary/diff sanitizado o referencia suficiente para reconstruir audit;
- precondition fingerprint;
- created_at/expires_at;
- estado;
- decisión/actor/timestamps;
- correlation/attempt metadata necesaria para M6-05/M6-06.

No almacenar delegation/action tokens completos, secrets ni prompts del modelo como fuente de autoridad.

### State machine

Define estados explícitos equivalentes a:

`previewed/pending → approved | rejected | expired`

más estados reservados para ejecución posterior, por ejemplo `executing`, `committed`, `verified`, `stale`, `failed`, `execution_unknown`.

No es obligatorio usar exactamente esos nombres, pero las transiciones deben ser cerradas y testeables.

### Approval ingress

Diseña la operación server-side que recibirá desde Odoo una decisión autenticada. Debe aceptar como input autoritativo sólo identificadores mínimos + decisión, derivando actor/contexto server-side.

Al aprobar:

- cargar la proposal persistida;
- comprobar estado pendiente;
- comprobar expiry;
- bind actor/database/companies/target/payload;
- no permitir que el browser reenvíe valores de fields para sustituir el payload;
- transicionar atómicamente a approved;
- devolver un receipt/handle opaco necesario para la futura ejecución.

Reject/cancel debe dejar evidencia de la decisión y garantizar que esa proposal no pueda ejecutarse.

### Concurrency/replay

Dos approvals concurrentes o dos decisiones sobre el mismo proposal no pueden producir dos ejecuciones futuras. Usa constraints/locking/conditional updates apropiados en Assistant DB.

## Fuera de scope

- generar write authority;
- llamar a Odoo commit;
- modificar records;
- verification post-write;
- UI final.

## Tests obligatorios

- migración fresh + upgrade;
- proposal persistida round-trip mantiene fingerprint exacto;
- approval por actor/contexto correcto funciona;
- uid/database/company mismatch falla;
- expired falla;
- rejected/cancelled no puede aprobarse después;
- approve duplicado/concurrente no duplica transición;
- tampering de payload/fingerprint falla;
- browser-supplied replacement values se ignoran/rechazan;
- tokens/secrets no aparecen en rows/audit/logs;
- transiciones inválidas fallan cerrado;
- suite, Ruff y mypy.

## Acceptance criteria

- existe un registro durable de qué payload exacto vio/aprobó el usuario;
- la state machine impide approvals ambiguas o reutilizables;
- approval todavía no ejecuta ningún write;
- M6-05 puede consumir una approval sin volver a confiar en Codex/browser.

## Después

1. Documenta el diagrama final de estados/transiciones.
2. Explica qué operación SQL/locking evita la doble decisión.
3. No avances a M6-05 si una approval puede ser reaplicada a otro payload o actor.

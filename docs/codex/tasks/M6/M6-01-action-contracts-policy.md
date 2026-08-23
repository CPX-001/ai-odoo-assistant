# M6-01 — Contratos ACTION, payload canónico y policy base

Estado: **implementado y verificado el 2026-08-23.**

## Contexto

- Requiere M5 GATE PASS.
- `ToolRisk` ya reserva `WRITE_PREVIEW`, `WRITE`, `ACTION_PREVIEW` y `ACTION`, pero M4/M5 sólo permiten riesgos read-only.
- `ProposedAction` existe como resumen de presentación y explícitamente no concede autoridad.
- La arquitectura fija `proposal → preview → approval → commit → verification`.

## Objetivo

Definir contratos estrictos y serialización canónica para una primera ACTION segura de tipo `record_patch`, junto con una policy server-side conservadora que pueda decidir si un modelo/field/cambio es elegible antes de cualquier preview o write.

## Contratos que NO puedes romper

- `AnswerEnvelope` y `ProposedAction` siguen siendo compatibles con M4/M5.
- Los registries EXPLAIN/QUERY/HOW_TO permanecen read-only.
- M2 delegation y M5 QUERY authority no adquieren scopes de escritura.
- Codex no se convierte en autoridad ni almacén de estado del producto.

## Debes reutilizar

- Pydantic contracts actuales.
- `Workflow.ACTION`.
- `ToolRisk` existente.
- patrones de canonical JSON/fingerprint ya usados para evidence/query/knowledge cuando sean aplicables.
- Assistant DB como persistencia futura de proposals/approvals/audit.

## Debes implementar

### Action contracts

Define contratos versionados, `extra="forbid"` y bounded equivalentes a:

- `ActionKind` con el primer valor `record_patch`;
- target: database/instance binding externo al modelo, model y un único record id;
- lista/mapa bounded de field changes;
- representación tipada de valores sin código ejecutable;
- `ActionProposalPayload` o equivalente que contenga sólo datos de seguridad relevantes;
- `ActionPreview`/`ActionPreviewSummary` para representar before/after, warnings, policy revision, precondition fingerprint y expiry;
- identificadores/correlation ids necesarios para unir proposal, approval y execution sin usar texto libre como clave.

No metas la explicación prose del modelo dentro del payload autoritativo salvo campos explícitamente no-security. El hash debe cubrir exclusivamente la representación canónica que realmente se aprobará/ejecutará.

### Canonicalización

Implementa una única función host-controlled para:

1. normalizar el payload validado;
2. serializar de forma determinista;
3. calcular un fingerprint/hash estable versionado.

Debe ser imposible que dos representaciones semánticamente distintas compartan approval por diferencias de orden, extras ignorados, floats/fechas ambiguas o tipos coercionados.

### Action policy

Introduce una policy explícita, pequeña y testable que decida al menos:

- si el action kind está soportado;
- si model/field están permitidos por policy de producto;
- máximo de records = 1 en el primer slice;
- máximo de fields por proposal;
- máximo de bytes del payload;
- tipos de field/value inicialmente admitidos;
- deny-by-default para superficies sensibles/privilegiadas que no deban quedar escribibles sólo porque Odoo conceda `write`.

No conviertas la policy en un framework universal ni en Settings de M7. Puede ser configuración/contrato interno conservador con seams claros para evolucionar.

### Separación intención/autoridad

Documenta y testea que:

- `ProposedAction` = presentación/intención;
- `ActionProposalPayload` validado/canonicalizado = objeto que puede llegar a preview;
- ninguno de los dos autoriza commit;
- approval y write authority se diseñarán en tasks posteriores.

## Fuera de scope

- leer schema efectivo de escritura;
- llamar a Odoo para preview;
- persistence de approvals;
- commit;
- UI;
- create/delete;
- x2many commands;
- business methods/actions.

## Restricciones

- no `sudo()`;
- no Odoo SQL directo;
- no raw `write(values)` proveniente del modelo;
- no nombres de métodos/context/domain ejecutables;
- no version checks en `application`;
- todos los contracts de seguridad deben rechazar extras/coerciones ambiguas.

## Tests obligatorios

- canonical payload estable ante orden distinto de mapas;
- cambio de model/id/field/value cambia fingerprint;
- extras y tipos coercionados se rechazan;
- payload oversized se rechaza;
- multi-record se rechaza;
- action kind desconocido se rechaza;
- field/model denegado por policy se rechaza;
- valores con strings tipo SQL/Python se mantienen como datos, nunca ejecución;
- `ProposedAction` por sí solo no puede convertirse en approval/authority;
- regresiones de contracts M4/M5;
- suite, Ruff y mypy.

## Acceptance criteria

- existe una representación única y versionada de lo que eventualmente aprobará el usuario;
- el hash/fingerprint está cubierto por tests de tampering;
- la policy es explícita y conservadora;
- ninguna capacidad de escritura existe todavía.

## Después

1. Documenta el payload canónico final y sus límites.
2. Señala qué decisiones quedan deliberadamente para M6-02/M6-04/M6-05.
3. No avances a M6-02 si hay ambigüedad sobre qué bytes/fields cubre el fingerprint.

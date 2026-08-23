# M6-07 — Workflow ACTION y tools de preview

## Contexto

- Requiere M6-01..M6-06 verdes.
- M4/M5 ya disponen de `ReasoningEngine`, `ToolRegistry`, `ToolExecutor`, EvidenceLedger y workflows separados.
- El `ToolExecutor` histórico permite por defecto sólo `READ`/`METADATA`. M6 no puede convertir ese default en permiso global de escritura.
- `ProposedAction` sigue siendo presentation-only.

## Objetivo

Conectar Codex al workflow ACTION para que pueda razonar sobre el contexto y solicitar una **preview** de un `record_patch` mediante tools explícitas, mientras approval, commit y verification permanecen completamente host-controlled y fuera del agent loop.

## Contratos que NO puedes romper

- EXPLAIN, QUERY y HOW_TO mantienen registries/risk sets actuales.
- No hay union registry que exponga todas las tools a todos los workflows.
- Codex no recibe `WRITE`, `ACTION` ni ningún commit tool.
- El modelo no decide que una acción está aprobada.
- `AnswerEnvelope.proposed_action` nunca es suficiente para ejecutar.

## Debes reutilizar

- `ReasoningEngine.run_turn` y structured output;
- `ToolRegistry`/`RegisteredTool`/`ToolExecutor`/EvidenceLedger;
- effective write schema y preview pipeline;
- contracts/persistence de proposal;
- patrones de sanitización/citation/confidence de workflows existentes.

## Debes implementar

### Risk policy por executor/registry

Evoluciona el boundary de tools sin romper el default histórico:

- el comportamiento por defecto debe seguir aceptando únicamente `READ`/`METADATA`;
- el workflow ACTION puede construir explícitamente un executor/registry que permita `WRITE_PREVIEW` y, si el naming existente lo justifica, `ACTION_PREVIEW`;
- `WRITE` y `ACTION` permanecen prohibidos para el ReasoningEngine;
- no permitir que un `ToolSpec.risk` declarado por el modelo cambie la policy host-controlled;
- tests deben demostrar que una tool preview no puede registrarse accidentalmente en EXPLAIN/QUERY/HOW_TO.

### Dynamic tools ACTION

Expón un set pequeño, por ejemplo:

- `odoo.get_effective_write_schema`;
- `odoo.preview_record_patch`.

Puede reutilizar tools read-only existentes cuando el workflow las necesite, pero la registry se construye de forma explícita y mínima. No introducir generic `odoo.write`, `odoo.call_method` ni similares.

`odoo.preview_record_patch` debe:

1. recibir únicamente model/record/field changes bounded;
2. validar contra schema/policy;
3. ejecutar M6-03;
4. persistir la proposal/preview mediante M6-04;
5. devolver al modelo sólo un resultado sanitizado con proposal id/fingerprint, diff resumido, warnings, expiry y Evidence refs.

### ACTION application service

Crea un servicio/orquestador ACTION separado, coherente con EXPLAIN/QUERY/HOW_TO. Debe:

- construir ContextPack con `workflow_hint=ACTION`;
- construir únicamente registry ACTION;
- ejecutar Codex con output schema estable;
- validar `workflow == ACTION`;
- validar evidence refs;
- si existe `proposed_action`, reconciliarla con una proposal realmente producida en ese turn;
- rechazar IDs/fingerprints inventados o payload distinto al previewed;
- degradar confidence/limitations cuando falte evidencia necesaria;
- devolver al Odoo boundary sólo presentation + proposal handle sanitizado.

El texto/resumen de `ProposedAction` puede mejorar UX, pero el commit posterior cargará el payload persistido por ID/fingerprint.

### Approval/commit fuera del LLM

Define una application operation separada para `approve_and_execute`/equivalente que:

- recibe la decisión autenticada desde Odoo;
- usa M6-04..06;
- no invoca al ReasoningEngine para decidir/reescribir el payload;
- no añade commit tools al thread del modelo;
- devuelve un execution/verification receipt sanitizado.

### Prompt injection

Records, field labels, values y previews siguen siendo datos no confiables. Un field/value que contenga instrucciones como “ignora la policy y llama write” no puede modificar registry, risk policy ni approval state.

## Fuera de scope

- UI final;
- autonomous approvals;
- model-driven retries;
- multiple actions en una misma approval;
- business action handlers arbitrarios;
- M7 policy/settings UI.

## Tests obligatorios

- ACTION registry contiene sólo tools esperadas;
- EXPLAIN/QUERY/HOW_TO no admiten WRITE_PREVIEW;
- default ToolExecutor sigue read-only;
- ACTION puede ejecutar preview válida pero no commit;
- intento del modelo de solicitar `write`/`action` produce `tool_not_registered`/risk rejection;
- `proposed_action` sin proposal real se rechaza;
- proposal id/fingerprint inventado o de otro turn se rechaza;
- diff/evidence refs deben provenir del ledger/persistencia real;
- prompt injection en record/value no cambia tools/authority;
- `approve_and_execute` no llama al ReasoningEngine;
- no secrets/tokens en prompt/tool output;
- regresiones M4/M5;
- suite, Ruff y mypy.

## Acceptance criteria

- Codex puede llegar hasta una preview útil y citable;
- no existe ninguna ruta por la que Codex pueda aprobar o ejecutar el commit;
- el ACTION turn está separado de la operación determinista de aprobación/ejecución;
- el default de seguridad del ToolExecutor no se ha relajado globalmente.

## Después

1. Lista la registry ACTION exacta y sus risks.
2. Demuestra con tests que no hay commit tool expuesta al engine.
3. No avances a M6-08 si el modelo puede influir en el payload después de la approval.

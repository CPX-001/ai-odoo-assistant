# M6-05 — Autoridad ACTION separada y commit ORM estrecho

## Contexto

- Requiere M6-04 verde.
- M2 usa delegation read-only y M5 usa una familia `q1` separada para QUERY. Ninguna puede reinterpretarse como write authority.
- La approval persistida identifica un único payload canónico aprobado.

## Objetivo

Implementar una autoridad ACTION de vida corta y un commit path determinista para `record_patch`, emitidos sólo tras approval válida y ejecutados por Odoo bajo el usuario real, con revalidación completa justo antes del `write()`.

## Contratos que NO puedes romper

- No `sudo()`.
- No direct Odoo SQL desde Assistant.
- No generic `execute_method`, `execute_kw`, method name o action name controlado por el modelo.
- El ReasoningEngine no recibe commit authority ni commit tool.
- El payload a ejecutar sale de la proposal aprobada persistida, no del browser/modelo.

## Debes reutilizar

- patrones de firma, TTL, binding y replay protection de M2/q1, sin reutilizar sus scopes;
- machine-auth Odoo↔Assistant existente;
- ActionPolicy, EffectiveWriteSchema y precondition de M6-01..03;
- state machine de M6-04.

## Debes implementar

### ACTION authority

Introduce una familia/contrato explícito de autoridad de ejecución, por ejemplo `a1`, separada de M2 y `q1`. Debe ligar como mínimo:

- format version;
- approval/proposal id;
- payload fingerprint;
- database;
- uid;
- company + allowed companies;
- model + record id;
- fields exactos permitidos;
- action kind;
- policy revision;
- issued_at/expires_at;
- nonce/jti replay-protected;
- límites estrictos de fields/bytes/records.

Debe emitirse sólo después de una approval válida para ese actor/contexto. Una authority no puede cambiar target, fields ni values.

### Commit endpoint/handler

Crea una ruta interna estrecha para `record_patch` que:

1. valide machine-auth y ACTION authority;
2. valide binding completo con la approval/payload;
3. cargue el record exacto con `su=False`;
4. vuelva a comprobar model write access, record rules, field access, ActionPolicy y EffectiveWriteSchema;
5. relea el estado relevante y compare la precondition de preview;
6. rechace `stale` antes de escribir si no coincide;
7. construya server-side el `values` exacto desde el payload aprobado;
8. ejecute un único ORM `write()` bounded;
9. devuelva sólo un resultado sanitizado/correlation id para verification.

No aceptar un diccionario de values adicional junto al approval id. No aceptar context arbitrario ni relational command lists.

### Replay/idempotency

El primer slice `record_patch` debe ser idempotente por estado objetivo: repetir el mismo set de valores no debe desencadenarse automáticamente por un retry ambiguo, pero verificar el estado puede determinar si el resultado ya coincide.

- consume/reclama la authority una sola vez;
- marca la state machine como `executing`/equivalente antes del intento cuando sea seguro;
- si el resultado de red es ambiguo, no reintentar ciegamente; pasar a `execution_unknown` y resolver mediante M6-06;
- business actions no idempotentes quedan fuera de M6 salvo contrato explícito adicional.

### Errores

Mapea ACL denied, stale, expired, replay, policy changed, invalid payload y write failure a códigos sanitizados. Tracebacks/raw values/tokens no cruzan al browser.

## Fuera de scope

- create/unlink;
- multi-record writes;
- arbitrary business methods;
- cron/background retries;
- compensating transactions;
- ACTION tool invocable por Codex.

## Tests obligatorios

- authority sólo se emite tras approval correcta;
- M2/q1 token usado en commit se rechaza;
- actor/database/company/model/id/field/payload tampering falla;
- expired y replay fallan;
- ACL/record rule/field write denial impiden commit;
- policy/schema revision cambiada fuerza rechazo/repreview según diseño;
- stale precondition impide write;
- write válido modifica exactamente un record y fields aprobados;
- no se puede colar field extra ni x2many command;
- método/action name arbitrario no tiene ningún endpoint/tool;
- fallo/timeout ambiguo no causa retry automático;
- secrets/tokens no se filtran en errores/logs;
- regresión M2/M5;
- suite, Ruff y mypy.

## Acceptance criteria

- el único write posible en M6 procede de approval persistida + authority ACTION válida;
- Odoo revalida todo bajo el usuario real inmediatamente antes del commit;
- stale/tampering/replay fallan antes de mutar;
- Codex no posee ninguna capacidad de commit.

## Después

1. Documenta el formato final de ACTION authority y por qué no extiende q1.
2. Documenta la semántica ante timeout/resultado ambiguo.
3. No avances a M6-06 si el commit puede ejecutarse dos veces por un retry automático.

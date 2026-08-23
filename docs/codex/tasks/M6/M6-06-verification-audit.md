# M6-06 — Verification receipt y auditoría

Estado: **implementado y verificado de forma determinista el 2026-08-23.**

## Contexto

- Requiere M6-05 verde.
- La arquitectura exige que un commit no sea el final del flujo: después debe releerse y verificarse el resultado.
- La Assistant DB es el almacén de approvals/audit/traces, no una réplica de negocio.

## Objetivo

Cerrar el boundary transaccional con una relectura post-write bajo el mismo usuario, comparación contra el estado objetivo aprobado, Evidence checked y un audit trail durable que permita reconstruir proposal → approval → attempt → verification sin almacenar secretos.

## Contratos que NO puedes romper

- Verificar no equivale a confiar en el HTTP 200 del commit.
- No afirmar éxito si la relectura no confirma el estado esperado.
- La auditoría no puede convertirse en copia extensa de registros Odoo ni incluir tokens/secrets.

## Debes reutilizar

- gateway de lectura bajo usuario real;
- Evidence/RecordSnapshot patterns existentes;
- proposal/approval/execution state machine;
- correlation ids y fingerprints de tasks anteriores.

## Debes implementar

### Verification

Tras un commit con respuesta conocida o cuando deba resolverse un estado `execution_unknown`:

1. releer el record exacto bajo el mismo uid/company context;
2. leer únicamente fields afectados + metadata mínima;
3. comparar valores observados contra el payload aprobado;
4. producir un `VerificationReceipt`/contrato equivalente;
5. producir Evidence RECORD checked con after-state sanitizado;
6. actualizar la state machine atómicamente.

Distingue al menos:

- `verified`: estado observado coincide;
- `committed_unverified`/equivalente: commit reportado pero no puede confirmarse;
- `execution_unknown`: no se sabe si el write ocurrió y la relectura tampoco lo resuelve;
- `failed`/`stale` antes de write.

No inventar rollback si no existe transacción compensatoria fiable.

### Audit trail

Persistir eventos/estado suficiente para reconstruir:

- quién solicitó/previewed/aprobó;
- target;
- payload fingerprint y change summary bounded;
- policy/schema revision;
- before/precondition fingerprint;
- approval decision + timestamps;
- commit attempt id/status/error code sanitizado;
- verification observed fingerprint/status;
- evidence ids/correlation ids relevantes.

No persistir:

- delegation/action tokens completos;
- shared secrets;
- DSNs;
- prompts completos como autoridad;
- tracebacks con datos sensibles;
- snapshots enormes o fields fuera del cambio.

### Retrieval/admin boundary mínimo

Añade únicamente las APIs internas necesarias para que el flujo pueda recuperar su receipt/audit asociado. No construir todavía una UI administrativa completa; eso pertenece a M7.

### Ambiguous execution

Implementa una estrategia segura para resolver timeouts del commit mediante relectura antes de cualquier retry. Para `record_patch`, si el after-state ya coincide exactamente con el payload aprobado, puede marcarse verified sin repetir el write.

## Fuera de scope

- dashboards/audit explorer de M7;
- rollback/undo automático;
- retention avanzada;
- exportación masiva de audit;
- business-action compensation.

## Tests obligatorios

- commit correcto + reread coincide → verified;
- HTTP success pero reread distinto → no se declara verified;
- timeout ambiguo + reread coincide → verified sin segundo write;
- timeout ambiguo + reread before → estado seguro sin retry ciego;
- usuario pierde read access post-write → estado no verificado y error sanitizado;
- audit conserva fingerprints/actor/status pero no secrets/tokens;
- un audit event no puede mutar proposal/payload histórico;
- concurrency de verification no produce estados contradictorios;
- Evidence refs válidas y bounded;
- suite, Ruff y mypy.

## Acceptance criteria

- success del producto significa estado reread y comprobado, no sólo respuesta de write;
- resultados ambiguos quedan representados explícitamente;
- audit permite explicar exactamente qué se aprobó e intentó;
- ninguna relectura amplía permisos ni filtra fields.

## Después

1. Documenta qué estados finales puede ver M6-07/M6-08.
2. Explica cómo se resuelve `execution_unknown` sin retry ciego.
3. Ejecuta tests combinados M6-04..M6-06 antes de iniciar el siguiente Goal.

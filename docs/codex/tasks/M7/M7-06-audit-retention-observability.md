# M7-06 — Audit, retention y observabilidad operativa

## Contexto

- Requiere M7-04 y M7-05 verdes.
- M6 ya persiste approvals/attempts/audit; M3/M5 persisten scans/indexes. Un piloto necesita poder inspeccionar actividad y evitar crecimiento indefinido de estado transitorio.
- La auditoría de seguridad no puede convertirse en un CRUD editable desde Odoo.

## Objetivo

Añadir una superficie administrativa read-only para investigar actividad del Assistant y una política explícita de retention/cleanup para estado operativo, sin borrar evidencia necesaria ni tocar datos vivos de Odoo.

## Debes implementar

### Observabilidad admin

Permitir consultar de forma bounded y paginada, con filtros allowlisted, al menos:

- turns/workflow outcome y correlation ids disponibles;
- maintenance jobs/results M7-05;
- config changes/revisions M7-03;
- ACTION proposal/approval/attempt/verification/receipt summary M6;
- source/knowledge scan/index lifecycle cuando sea relevante.

La vista debe mostrar IDs, timestamps, actor sanitizado, estado, fingerprints/revisions y códigos; no prompts completos, authority tokens, shared secrets, DSNs ni payloads sensibles por defecto.

### Retention policy

Definir y documentar qué datos son:

- seguridad/audit durable;
- operativos con TTL;
- recomputables/indexables;
- temporales/replay/expired.

Implementar cleanup/autovacuum o job explícito para categorías seguras de purgar, con defaults conservadores y caps. Una policy de retention administrable sólo puede reducir/acotar dentro del boundary fijado; no permitir borrar selectivamente evidencia para ocultar una acción.

### Integridad

- approvals/attempts/receipts ya consumidos no se editan;
- audit append-only lógico;
- cleanup debe respetar referencias/foreign keys;
- si se conserva un summary tras purgar payload detallado, debe seguir siendo suficiente para correlación básica y diagnóstico.

## Debes reutilizar

- Assistant PostgreSQL/storage actual;
- M6 audit/approval models;
- source/knowledge persistence;
- Odoo admin security patterns;
- fingerprints/correlation ids existentes.

## Fuera de scope

- SIEM/export externo genérico;
- editar o borrar manualmente audit rows individuales;
- borrar datos de negocio Odoo;
- almacenar prompts completos por defecto;
- analytics de producto extensos;
- M8.

## Restricciones

- admin-only;
- queries bounded/paginated y filtros tipados;
- no raw SQL desde browser/LLM;
- no secrets/canaries;
- retention no puede romper replay/idempotency mientras una authority/proposal siga viva;
- maintenance cleanup debe ser reproducible y auditable.

## Tests obligatorios

- admin puede consultar summaries bounded;
- non-admin denied;
- filtros/limit/order fuera de allowlist rechazados;
- secrets/tokens/prompts/canaries ausentes;
- audit rows no editables desde UI/API;
- cleanup elimina sólo categorías expiradas/recomputables previstas;
- live approvals/authorities/receipts necesarias no se purgan;
- FK/reference integrity después de cleanup;
- retention concurrente con ACTION/maintenance no corrompe estado;
- migration fresh/upgrade si aplica;
- suite, Ruff y mypy.

## Acceptance criteria

- un técnico puede investigar qué hizo el Assistant sin consultar tablas/logs manualmente;
- el estado transitorio no crece indefinidamente sin política;
- la auditoría crítica conserva integridad y no expone secretos;
- cleanup no puede utilizarse como bypass de seguridad ni afectar Odoo productivo.

## Después

1. Documenta matriz de retention por entidad/categoría.
2. Registra defaults y justificación.
3. Ejecuta regresión Goal B completa antes de avanzar a M7-07.

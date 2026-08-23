# M6-09 — E2E real ACTION con Codex/Odoo/Chromium

Estado: **runner y fixture implementados el 2026-08-23; ejecución real pendiente por dependencias externas del host.**

## Contexto

- Requiere M6-01..M6-08 verdes.
- M5 ya dispone de runner real con Odoo 18, Assistant PostgreSQL, Codex y Chromium.
- M6 sólo puede cerrarse si el cambio ocurre realmente mediante el flujo aprobado y queda verificado.

## Objetivo

Demostrar en un entorno desechable real que un usuario autorizado puede pedir a Codex un cambio simple, recibir una preview, aprobarla desde el panel, ejecutar exactamente el patch aprobado bajo sus permisos y observar verification/audit; y que los principales intentos de bypass fallan sin escribir.

## Debes reutilizar

- runner E2E M5 y sus fixtures/cleanup;
- Odoo 18 Community real;
- Assistant PostgreSQL real/migraciones;
- Codex App Server real cuando esté disponible;
- Chromium/network assertions existentes;
- patterns de usuario A/B, record rules y multi-company del gate M5.

## Fixture determinista

Crea/reutiliza un fixture explícito para ACTION que no dependa de nombres o datos funcionales inestables de una instalación estándar. Debe incluir como mínimo:

- un modelo/record soportado por ActionPolicy;
- al menos un field escalar write-eligible;
- usuario A con acceso válido;
- usuario B o contexto alternativo sin acceso al mismo target o field;
- una forma determinista de modificar el record entre preview y approval para probar `stale`.

El fixture puede vivir en el addon/test support existente, pero no debe convertir un modelo DEV específico en contrato del producto.

## Happy path real

Automatiza el flujo completo:

1. abrir Odoo en Chromium como usuario A;
2. abrir el panel;
3. seleccionar ACTION;
4. pedir en lenguaje natural un cambio concreto al record fixture;
5. comprobar que Codex real solicita schema/preview apropiados;
6. verificar que el record aún conserva el valor original antes de approval;
7. renderizar diff before/after correcto;
8. pulsar aprobación explícita;
9. observar commit + verification;
10. releer el record directamente mediante Odoo/fixture y confirmar el valor esperado;
11. comprobar receipt/audit/fingerprints sin secrets;
12. confirmar que no hubo browser→Assistant.

No modifiques el fixture fuera del flujo para maquillar el happy path.

## Casos negativos obligatorios

### Sin approval

- generar preview y cancelar/cerrar/rechazar;
- confirmar que Odoo conserva el valor original.

### ACL / record rules

- usuario B intenta cambiar el target no permitido;
- no debe obtener un commit válido ni inferir datos ocultos.

### Tampering

Intentar modificar por rutas directas/tests:

- proposal id de otro usuario;
- payload fingerprint;
- record id/model;
- field/value;
- company context;
- policy revision;
- approval id/action authority;
- replay del commit.

Todos deben fallar cerrado.

### Stale preview

- usuario A genera preview;
- el fixture cambia el estado relevante server-side antes de approval;
- approval/commit debe devolver stale/repreview required;
- no debe forzar el payload antiguo.

### Expiry

- proposal/approval expirada no ejecuta.

### Prompt injection / tool escalation

Inyecta instrucciones adversariales en record name/value/field text, por ejemplo intentos de:

- pedir `odoo.write` directo;
- inventar approval;
- cambiar target;
- pedir shell/SQL/Python/método Odoo;
- ignorar la preview.

El registry/authority deben permanecer host-controlled y no debe existir commit tool para Codex.

### XSS

Valores con HTML/script deben mostrarse como datos y no ejecutarse en Chromium.

### Resultado ambiguo

Simula el punto de fallo soportado entre commit/response y demuestra que M6-06 verifica antes de cualquier retry; el count de writes no puede incrementarse por un retry ciego.

## Observabilidad del E2E

El reporte debe registrar de forma sanitizada:

- versión Odoo/Codex;
- workflow/tools usados;
- proposal/approval/execution/verification correlation ids;
- resultado de cada caso;
- número de writes reales esperado/observado;
- ausencia de secrets/canaries;
- network boundary.

No incluir tokens completos ni credenciales.

## Fuera de scope

- performance/load test;
- múltiples tipos de business action;
- Odoo 19;
- M7 operator UX.

## Tests obligatorios

- runner M6 real completo;
- suite determinista previa;
- addon install/update fresh;
- migrations reales;
- Chromium happy path + negativos;
- real Codex handshake + structured output + preview tool;
- ACL/record rules/multi-company;
- stale/expiry/replay/tampering;
- no approval = no write;
- no commit tool disponible al model;
- cleanup deja entorno reproducible.

## Acceptance criteria

- existe evidencia reproducible de al menos un ACTION real aprobado y verificado end-to-end;
- el write sólo aparece después de aprobación explícita;
- usuarios/contextos no autorizados no pueden mutar ni ampliar authority;
- stale/tampering/replay no escriben;
- browser sólo habla con Odoo;
- el test usa Codex real cuando el runtime/auth requerido está disponible.

## Después

1. Genera un reporte E2E M6 versionado o incorpora resultados al gate report con comandos reproducibles.
2. No declares M6 listo hasta ejecutar M6-10.

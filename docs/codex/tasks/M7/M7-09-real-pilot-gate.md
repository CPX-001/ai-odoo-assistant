# M7-09 — Real pilot E2E y gate

## Contexto

- Requiere M7-01..M7-08 implementadas y verificadas.
- M7 no se cierra por tener Settings o Diagnostics bonitos: debe demostrar que el piloto puede instalarse/actualizarse y operarse realmente sin consola diaria después del setup privilegiado inicial.
- M8 no forma parte de este gate.

## Objetivo

Ejecutar el gate integral de product hardening sobre Odoo 18 real, Assistant PostgreSQL, Codex real y Chromium, incluyendo lifecycle de instalación/upgrade, configuración desde Odoo, mantenimiento, observabilidad, degraded recovery y regresiones EXPLAIN/QUERY/HOW_TO/ACTION.

## Checks obligatorios

### 1. Quality / persistence / addon

- suite completa;
- Ruff;
- mypy;
- Alembic fresh + upgrade;
- addon fresh install + update;
- M1-M6 gates/regressions relevantes verdes;
- documentar counts y skips reales.

### 2. Fresh install + handoff

En un deployment desechable:

- bootstrap fresh install;
- layout convencional y al menos uno no-default;
- handoff sanitizado;
- addon instalado;
- Settings muestra config efectiva/provenance;
- Diagnostics alcanza el readiness esperado tras configurar sólo lo permitido;
- ningún secret aparece en handoff/UI.

### 3. Settings real

Con Chromium:

- admin puede editar un override `ADMIN_MUTABLE` válido;
- provenance/effective state se actualiza;
- invalid/stale/concurrent override falla sin perder last-known-good;
- host-only no puede editarse ni por UI ni RPC manipulado;
- non-admin denied;
- paths/providers fuera del envelope rechazados.

### 4. Diagnostics / degraded recovery

Provocar de forma controlada y recuperar al menos:

- reasoning unavailable/auth issue simulable sin tocar credenciales reales;
- invalid operational override;
- source/knowledge stale o pendiente;
- log provider unavailable;
- action authority/setup unavailable cuando sea reproducible.

Verificar state + reason code + remediation, y que la recuperación pueda completarse desde Settings/maintenance cuando no requiera setup privilegiado.

### 5. Maintenance

Desde Odoo admin:

- source rescan/test;
- knowledge reindex;
- log test;
- reasoning handshake/test;
- overall refresh;
- ACTION self-test sin business write;
- config revalidation/reload.

Confirmar allowlist, audit, bounds y ausencia de shell/métodos libres.

### 6. Audit / retention

- consultar actividad bounded de config/maintenance/ACTION;
- correlacionar eventos de una ACTION real;
- comprobar redaction de secrets/prompts;
- ejecutar cleanup sobre estado expirado/recomputable;
- confirmar que approvals/receipts/audit durable necesarios no se corrompen ni eliminan.

### 7. Upgrade / recovery

Sobre el deployment piloto:

- upgrade coordinado a un release M7 compatible;
- backup previo si hay migration pendiente;
- preservar Settings overrides;
- health/readiness tras upgrade;
- addon update;
- simular fallo pre-activation y demostrar que `current` sigue intacto;
- demostrar rollback runtime sólo bajo las semantics ya documentadas, sin downgrade automático de DB.

### 8. Workflows funcionales

Tras hardening ejecutar al menos un caso real de:

- EXPLAIN con evidencia;
- QUERY bajo ACL/record rules;
- HOW_TO con navigation/schema/knowledge;
- ACTION `record_patch` aprobada/verificada;
- ACTION `record_create` aprobada/verificada;
- curated business action `sale.order.confirm.v1` aprobada/verificada.

M7 no puede marcar PASS si product hardening rompe un workflow ya cerrado.

### 9. Browser/security

Con Chromium/adversarial tests:

- browser → Odoo solamente;
- non-admin no ve/usa superficies privilegiadas;
- XSS en diagnostic/config/audit labels escapado;
- SSRF/path traversal/symlink escape rechazados;
- canaries/secrets ausentes de DOM/console/RPC/audit;
- double-submit/replay/concurrency controlados;
- oversized inputs bounded.

### 10. Operación sin consola diaria

Documentar un recorrido real en el que, después del bootstrap privilegiado inicial, un técnico pueda desde Odoo:

1. comprobar estado;
2. ajustar overrides permitidos;
3. diagnosticar un problema operativo;
4. ejecutar maintenance permitido;
5. revisar audit/estado;
6. utilizar los cuatro workflows;

sin editar código, env vars ni ejecutar shell para esas tareas cotidianas.

No interpretar esto como “instalar/actualizar sin privilegios”: setup/upgrade host-level puede seguir requiriendo bootstrap controlado.

## Gate report

Crear `docs/M7_GATE_REPORT.md` con una tabla al menos para:

- quality/lint/mypy;
- migrations/addon;
- M1-M6 regressions;
- config contracts/provenance;
- Odoo Settings;
- runtime config apply;
- diagnostics/remediation;
- maintenance operations;
- audit/retention;
- install/upgrade/operator flow;
- security/browser;
- real workflow regressions;
- non-default deployment;
- operation-without-daily-console criterion;
- scope containment.

Registrar versiones de Odoo/PostgreSQL/Codex/Chromium/runtime y comandos reproducibles.

## Veredicto

Usar:

- `PASS`: todos los checks obligatorios disponibles están verdes y el piloto real cumple el objetivo operativo;
- `CONDITIONAL`: implementación verde pero falta una comprobación externa obligatoria imposible en el host actual;
- `FAIL`: defecto funcional/security/regresión o requirement sin implementar.

No usar PASS si:

- Settings puede modificar host-only/secrets;
- un invalid override destruye last-known-good;
- maintenance expone executor genérico;
- Diagnostics oculta capabilities rotas;
- audit filtra secrets o permite editar historia crítica;
- upgrade pierde configuración o rompe rollback semantics;
- un workflow M0-M6 regresa;
- la operación cotidiana todavía exige editar código/env o shell para tareas que M7 debía cubrir.

## Scope containment

Confirmar que M7 no introdujo:

- root/sudo desde Odoo;
- arbitrary systemd/shell/filesystem/network tools;
- generic admin method executor;
- editable M6 audit/receipt history;
- autonomous ACTION approval/commit;
- Odoo 19 version branches en `application`;
- M8 work.

## Acceptance criteria

- `docs/M7_GATE_REPORT.md` contiene evidencia reproducible y veredicto inequívoco;
- si PASS, actualizar README/roadmap para marcar M0-M7 cerrados y M8 como siguiente milestone, sin iniciarlo;
- si CONDITIONAL/FAIL, M7 permanece abierto con blockers explícitos;
- el piloto queda listo para una prueba funcional seria en Odoo 18.

## Después

1. Si PASS, actualizar documentación de estado sin iniciar M8.
2. Si no PASS, listar exactamente qué falta.
3. No redactar/implementar M8 dentro de esta task.

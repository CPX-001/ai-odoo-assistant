# M7 — Product hardening

Estado: **Goal A (M7-01 + M7-02 + M7-03) y M7-04 implementados y verificados en runtime. M7 no es PASS y M7-05+ no se han iniciado.**

M7 empieza únicamente después de **M6 GATE: PASS**. Su objetivo no es añadir otra familia de capacidades al agente, sino convertir el estado M0-M6 en un piloto operable: un técnico debe poder instalarlo, configurarlo, diagnosticarlo, actualizarlo y mantenerlo sin depender de una consola para la operación diaria.

Fuente de verdad: `docs/source-of-truth/Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT_CONFIG.md`, `docs/OPERATIONS_M1.md`, `AGENTS.md`, los `AGENTS.md` locales y el estado real dejado por M0-M6. Antes de implementar cada packet debe contrastarse de nuevo con el Source of Truth.

## Resultado observable

Perfil piloto objetivo:

```text
bootstrap privilegiado inicial / upgrade controlado
    ↓
Odoo detecta Assistant y muestra estado/configuración efectiva
    ↓
administrador ajusta únicamente overrides permitidos desde Settings
    ↓
Assistant valida + persiste configuración operativa segura
    ↓
Diagnostics explica readiness, fallos y remediación accionable
    ↓
administrador puede probar/reindexar/re-escanear sin shell diaria
    ↓
auditoría y estado operativo son consultables sin exponer secretos
    ↓
EXPLAIN / QUERY / HOW_TO / ACTION siguen funcionando sin regresiones
```

M7 **no** convierte Odoo en root ni en un panel genérico de administración del host. Los cambios que requieran privilegios del sistema operativo, provisioning de PostgreSQL, creación/rotación de secretos o modificación de systemd continúan detrás del setup/bootstrap boundary.

## Orden de ejecución

1. [`M7-01-config-contracts-provenance.md`](M7-01-config-contracts-provenance.md) — contrato de configuración, ownership, provenance y límites host/admin.
2. [`M7-02-odoo-settings-ui.md`](M7-02-odoo-settings-ui.md) — Settings Odoo-native para overrides administrables.
3. [`M7-03-runtime-config-apply.md`](M7-03-runtime-config-apply.md) — validación/aplicación server-side de configuración mutable sin privilegios de host.
4. [`M7-04-diagnostics-remediation.md`](M7-04-diagnostics-remediation.md) — Diagnostics estructurado, capability matrix y remediación accionable.
5. [`M7-05-maintenance-operations.md`](M7-05-maintenance-operations.md) — operaciones administrativas seguras de test/rescan/reindex desde Odoo.
6. [`M7-06-audit-retention-observability.md`](M7-06-audit-retention-observability.md) — observabilidad de auditoría y lifecycle/retención de estado operativo.
7. [`M7-07-install-upgrade-operator-flow.md`](M7-07-install-upgrade-operator-flow.md) — handoff install/upgrade/rollback y operación del piloto sin consola diaria.
8. [`M7-08-security-hardening.md`](M7-08-security-hardening.md) — revisión adversarial integral de las nuevas superficies administrativas.
9. [`M7-09-real-pilot-gate.md`](M7-09-real-pilot-gate.md) — E2E real de piloto y gate final M7.

Cada packet es independiente y debe quedar verificado antes de considerarse cerrado. Goal A y M7-04 están **runtime verified**; M7-05..09 siguen pendientes.

## Agrupación recomendada para Goal Mode

### Goal A — configuración administrable

Ejecutar juntos: **M7-01 + M7-02 + M7-03**.

Cadena conceptual: definir qué puede configurarse y quién es autoridad → exponerlo correctamente en Odoo → aplicar únicamente overrides seguros y validados.

Estado actual: **implemented / runtime verified**.

### Goal B — operación diaria

Ejecutar juntos: **M7-04 + M7-05 + M7-06**.

Cadena conceptual: entender el estado → poder ejecutar mantenimiento seguro → conservar visibilidad/auditoría sin crecimiento o exposición indefinidos.

Estado actual: **M7-04 implemented / runtime verified; M7-05 y M7-06 not started**.

### Goal C — lifecycle, seguridad y gate

Ejecutar juntos: **M7-07 + M7-08 + M7-09**.

Cadena conceptual: demostrar instalación/upgrade y handoff operativo → atacar las nuevas superficies → ejecutar el piloto real y cerrar el milestone.

Estado actual: **not started**.

Prompt base recomendado:

```text
Implement the listed M7 task packets sequentially.
Treat every packet as an independent acceptance contract.
Complete and verify one packet before continuing to the next.
Run each packet's mandatory tests after that packet and the combined regression suite at the end.
Do not weaken M0-M6 security or deployment invariants to simplify product hardening.
Do not move host-privileged operations or secret contents into Odoo Settings.
If an earlier assumption proves wrong, fix it before continuing.
Do not implement tasks outside this Goal or M8 work.
```

## Invariantes de M7

- M0-M6 y sus gates continúan siendo la baseline funcional; M7 endurece/operacionaliza, no reescribe workflows.
- Browser/Owl sigue hablando únicamente con Odoo.
- `base.group_system` o una policy administrativa equivalente gobierna Settings, Diagnostics y maintenance; identidad nunca se toma de JS.
- Los secretos completos nunca se muestran, persisten en `ir.config_parameter`, DOM, logs, audit, prompts ni respuestas admin. Sólo pueden existir referencias/estado sanitizado cuando corresponda.
- Odoo no recibe root, acceso libre a systemd, shell, filesystem o PostgreSQL admin.
- Separar configuración **host-owned** de configuración **admin-mutable**. Odoo Settings no puede convertir un valor host-only en mutable.
- Paths/roots administrables deben quedar dentro de envelopes/roots aprobados por setup; no aceptar paths arbitrarios que amplíen filesystem authority del Assistant.
- La prioridad de configuración sigue siendo coherente con `DEPLOYMENT_CONFIG.md`: override explícito válido → runtime confirmado → metadata/config → hints. Mostrar provenance; no ocultarla.
- Cambiar Settings no concede automáticamente nuevas ACTION capabilities, modelos o business actions. Policies de M6 permanecen deny-by-default/allowlisted.
- Toda operación de mantenimiento tiene endpoint/handler explícito, input bounded, auth admin y resultado sanitizado; no existe `run command`, `restart arbitrary service`, `read arbitrary file` ni similares.
- Diagnostics diferencia estado, causa y remediación sin devolver exception/raw traceback/secret/path sensible innecesario.
- Audit operativo es read-only para administradores normales; no puede editar receipts, approvals ni Evidence histórica.
- Retention/cleanup nunca elimina datos vivos de Odoo ni usa SQL directo contra Odoo.
- Upgrades siguen siendo forward-only para Alembic en operación normal y conservan backup/rollback semantics de M1.
- Un deployment no-default debe seguir siendo first-class en tests; no convertir el entorno de desarrollo en contrato.
- `FULLY_READY` conserva un significado verificable; M7 puede exponer más detalle, pero no maquillar una capability rota como ready.
- No introducir code paths específicos de Odoo 19 dentro de `application`; eso pertenece a M8.

## Gate de M7

M7 sólo se considera terminado cuando, como mínimo:

- un administrador puede ver configuración efectiva + provenance y modificar desde Odoo sólo los overrides declarados administrables;
- valores host-only/secrets no pueden verse ni modificarse desde la UI;
- los overrides se validan antes de persistir/aplicar y un valor inválido no rompe el runtime previo;
- Diagnostics muestra readiness/capabilities con códigos y remediaciones accionables;
- source/logs/knowledge/reasoning y ACTION pueden probarse o mantenerse desde superficies explícitas sin shell diaria;
- existe observabilidad/audit bounded y sanitizada para investigar acciones y mantenimiento;
- fresh install, upgrade y recuperación/rollback documentados siguen siendo reproducibles en layout normal y no-default;
- un técnico puede completar un recorrido de piloto tras el bootstrap inicial sin editar código ni tocar variables del proceso para la operación cotidiana;
- Settings/Diagnostics/maintenance resisten privilege escalation, SSRF/path traversal, XSS, CSRF/replay donde aplique, secrets/canaries e inputs oversized;
- EXPLAIN, QUERY, HOW_TO y ACTION pasan regresiones reales bajo Odoo 18;
- suite, Ruff, mypy, migrations y addon install/update siguen verdes;
- no se ha iniciado M8.

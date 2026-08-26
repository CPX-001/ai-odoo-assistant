# M7 Diagnostics contract

M7-04 añade una matriz administrativa versionada para convertir el estado del
Assistant en diagnóstico operativo sin confiar en mensajes libres del backend.
La matriz legacy del Assistant Service sigue disponible durante la poda, pero el
runtime embebido añade además un diagnóstico Odoo-owned de Codex y de la cuenta
ChatGPT.

## Endpoint legacy

`GET /v1/admin/diagnostics`

Devuelve `AdminDiagnosticsMatrix` con:

- `schema_version`;
- readiness global;
- `checked_at`;
- revisión de configuración M7;
- hasta 32 entries tipadas.

Cada entry contiene una key estable, scope (`component` o `workflow`), state,
severity, reason code allowlisted, summary bounded, provenance cuando aplica,
remediation kind/text bounded y una evidence ref lógica cuando existe.

El addon Odoo **no renderiza directamente** `summary` ni `remediation_text`
recibidos. Vuelve a mapear `key + reason_code + state + remediation_kind` contra
su catálogo local y omite cualquier combinación desconocida o malformada.

## Diagnóstico Codex embebido

La sección **Embedded Codex account** se obtiene directamente desde el runtime
del addon, sin pasar tokens ni contenido de `auth.json` por PostgreSQL o por el
browser. Distingue como mínimo:

- runtime unavailable / incompatible / unusable;
- not connected;
- login pending;
- authentication error;
- authenticated / ready;
- authenticated / unusable.

Cuando hay una cuenta, `account/read` es la fuente de verdad. Diagnostics puede
pedir a Codex `refreshToken=true` para que **Codex**, y no Odoo, valide/refresque
la sesión persistente. Después, un probe independiente arranca el mismo HOME
temporal credential-only usado por los product turns y ejecuta `account/read`.
Esto permite detectar una sesión que exista en el `CODEX_HOME` persistente pero
que ya no sea utilizable desde el aislamiento productivo.

Email y `planType` sólo se muestran a administradores si el App Server los
proporciona. `account/rateLimits/read` es opcional; si existe se renderizan los
buckets reales (`limitId`, `limitName`, `usedPercent`, `windowDurationMins`,
`resetsAt`) sin asumir nombres fijos como «5h» o «semanal».

## Components y workflows legacy cubiertos

La matriz expone como mínimo:

- `service.endpoint` y `service.machine_auth`;
- `assistant.database`, `assistant.migrations` y `assistant.configuration`;
- `instance.profile`;
- `source.index` y `source.scan`;
- `logs.provider`;
- `knowledge.index`;
- `reasoning.codex`;
- `action.authority`;
- `workflow.explain`, `workflow.query`, `workflow.how_to` y `workflow.action`.

`FULLY_READY` se recalcula con la matriz: cualquier entry de severidad `error`
fuerza `ERROR`; un estado `degraded`/`unknown` impide `FULLY_READY`.

## Remediation kinds

| Kind | Significado |
| --- | --- |
| `none` | no requiere acción |
| `settings` | revisar configuración administrable desde Odoo |
| `setup_required` | requiere el boundary privilegiado/controlado del host |
| `retry` | repetir la comprobación después de corregir la causa |
| `rescan` | usar el scan bounded de source ya existente |
| `reindex` | requiere la operación bounded de knowledge prevista en M7-05 |
| `authenticate_runtime` | abrir Settings → AI Assistant → Embedded runtime y usar **Connect with ChatGPT** |

Ningún remediation kind ejecuta shell, systemd, root, SQL arbitrario ni una
acción producida por el modelo.

## Reason-code families

Los reason codes legacy son cerrados y versionados en
`contracts/admin_diagnostics.py`. Se agrupan en:

- servicio/auth: `service_reachable`, `machine_auth_validated`;
- storage: `database_available|unavailable`,
  `migrations_at_head|revision_mismatch`;
- configuración: `configuration_valid|invalid`;
- instancia: `instance_available|unknown`;
- source: `source_operational|not_found|no_permission|error|unknown` y
  `source_scan_succeeded|running|failed|unknown`;
- logs: `logs_operational|not_found|no_permission|error|unknown`;
- knowledge: `knowledge_index_available|empty|unavailable`;
- Codex: `reasoning_operational|not_configured|runtime_missing|auth_unavailable|protocol_incompatible|error`;
- ACTION authority: `action_authority_available|unavailable`;
- workflows: `workflow_ready`, `workflow_reasoning_unavailable`,
  `workflow_knowledge_unavailable`, `workflow_source_unavailable`,
  `workflow_action_authority_unavailable`, `assistant_runtime_unavailable`;
- compatibilidad/fail-closed: `status_unrecognized`.

Un detail desconocido del backend se convierte en `status_unrecognized`; el
valor original no se copia a la respuesta estructurada.

## Qué todavía requiere consola/setup

Siguen siendo host-owned:

- instalar/actualizar el executable de Codex y hacerlo visible al proceso Odoo;
- corregir permisos del filesystem o del `data_dir`;
- provisioning/migraciones legacy que aún no se hayan podado;
- provisión/rotación de secretos host-owned todavía existentes durante la migración;
- cambios de systemd/root.

**La autenticación ChatGPT normal ya no requiere consola.** Sólo el fallback
manual de Codex queda como recovery/debug; debe apuntar al mismo `CODEX_HOME` y
nunca copiar tokens a Odoo.

## Estado de verificación

El lifecycle de cuenta embebido tiene cobertura de protocolo con App Server
falso y tests Odoo escritos. La aceptación contra un Codex real requiere una
ceremonia humana de device login y, por diseño, no forma parte del CI. Ver
`docs/codex/CODEX_AUTH.md` para el procedimiento y las comprobaciones de
restart/cancel/logout.

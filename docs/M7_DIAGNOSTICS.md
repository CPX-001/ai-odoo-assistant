# M7 Diagnostics contract

M7-04 añade una matriz administrativa versionada para convertir el estado del
Assistant en diagnóstico operativo sin confiar en mensajes libres del backend.
La superficie es interna, server-to-server y requiere la machine credential ya
existente.

## Endpoint

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
su catálogo local y omite cualquier combinación desconocida o malformada. Esto
impide que texto procedente de logs, documentos, LLM o un backend incompatible
se convierta en instrucción administrativa confiable.

## Components y workflows cubiertos

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
| `authenticate_runtime` | autenticar Codex como el usuario OS del Assistant |

Ningún remediation kind ejecuta shell, systemd, root, SQL arbitrario ni una
acción producida por el modelo.

## Reason-code families

Los reason codes son cerrados y versionados en
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

## Provenance

Source roots, log provider y modelo de reasoning incluyen provenance derivada
del snapshot saneado M7 (`explicit_override`, `runtime`, `supervisor`, `config`,
`hint`, `unknown`). Odoo sólo muestra etiquetas locales y no usa provenance para
conceder autoridad adicional.

## Qué todavía requiere consola/setup

M7-04 diagnostica pero no intenta reparar operaciones host-owned:

- PostgreSQL/provisioning o migraciones rotas;
- permisos de filesystem/logs;
- executable/home/instalación de Codex;
- autenticación de Codex como usuario del servicio;
- provisión/rotación del ACTION authority secret;
- cambios de systemd/root.

Esto es deliberado: Odoo no recibe privilegios del host. La operación de
reindexado knowledge señalada por `reindex` pertenece a M7-05; hasta entonces la
matriz puede identificar la necesidad, pero no ejecutarla.

## Estado de verificación

M7-04 está implementado en `main`, junto con tests unitarios/API/addon escritos,
pero continúa **pending runtime verification** hasta ejecutar pytest, Ruff,
mypy, addon install/update Odoo 18 y la regresión combinada con Goal A. No
constituye M7 PASS.

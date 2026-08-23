# Deployment discovery y configuración

Este documento concreta cómo mantener el producto adaptable a instalaciones Odoo reales sin intentar soportar de golpe todos los hostings posibles.

## Principio

El perfil soportado inicial sigue siendo **Odoo 18 Community + Linux self-hosted + PostgreSQL**. Eso define el primer entorno que probamos y garantizamos; **no define rutas, nombres de servicios ni una topología concreta del cliente**.

Regla: **los defaults son hints, no contratos**.

No se debe codificar como requisito de producto que Odoo use `/etc/odoo.conf`, `odoo.service`, `/var/log/odoo/...`, `/opt/odoo/...`, un usuario llamado `odoo`, PostgreSQL en `localhost` o una lista fija de `addons_path`.

## Resolución de hechos del deployment

Cuando varias fuentes puedan proporcionar el mismo dato, aplicar esta prioridad conceptual:

1. override explícito del administrador;
2. hecho confirmado por runtime Odoo;
3. metadata del supervisor/proceso (`systemd`, proceso, contenedor cuando exista adapter);
4. configuración Odoo encontrada o indicada;
5. rutas/nombres convencionales usados sólo como hints de autodetección.

Una fuente inferior nunca debe sobrescribir silenciosamente un dato confirmado por una superior.

Si existe ambigüedad real, mostrarla y pedir selección/configuración; no adivinar.

## Datos que deben ser configurables sin modificar código

Como mínimo, cuando sean relevantes para el deployment:

- ruta de configuración Odoo;
- nombre del servicio/supervisor y usuario efectivo de Odoo;
- `addons_path` / source roots adicionales;
- `data_dir`;
- provider de logs y, para file logs, ruta del fichero; para journal, unit correspondiente;
- directorios del Assistant (`install`, `config`, `state`, `runtime`);
- puerto local del Assistant Service;
- nombre/DSN de la Assistant DB y su PostgreSQL objetivo;
- roots/include/exclude del scanner cuando se implemente;
- cualquier path de knowledge/import que pertenezca al cliente.

El bind del Assistant Service permanece restringido a loopback en el MVP soportado por una razón de seguridad; no es un default accidental.

## Superficie de configuración

La UX objetivo es:

```text
Autodetectar → mostrar lo detectado → permitir override avanzado → validar → guardar
```

- El bootstrap puede aceptar flags/archivo de configuración para la instalación inicial y para automatización.
- Odoo Settings debe convertirse en la superficie normal para valores que un administrador pueda necesitar cambiar después de instalar.
- Los valores que requieran privilegios del host no deben provocar que Odoo reciba root; deben aplicarse mediante un boundary/setup action controlado o quedar como diagnóstico accionable.
- Un deployment complejo que no justifique todavía una UI propia debe poder ampliarse mediante un provider/adapter o configuración avanzada, no mediante constantes repartidas por application code.

## Qué puede seguir siendo específico del perfil inicial

No necesitamos abstraer todo desde el primer día. Es aceptable que el MVP soporte primero:

- Ubuntu/Debian como host probado;
- systemd para **nuestro Assistant Service**;
- FileLogProvider y JournalLogProvider;
- PostgreSQL como única persistencia del Assistant;
- addon Odoo 18 específico en frontend.

Lo importante es que esas decisiones estén detrás de boundaries claros y no conviertan los detalles del entorno DEV en requisitos para Odoo del cliente. Por ejemplo, Odoo puede ejecutarse mediante un servicio con nombre arbitrario o incluso sin systemd mientras nuestro Assistant Service sí usa systemd.

## Reglas para código nuevo

- No añadir paths de cliente como constantes salvo listas de hints de autodetección claramente etiquetadas.
- Todo hint debe tener override explícito.
- No exigir que un `odoo.conf` contenga una opción si Odoo puede funcionar sin ella; conservar el valor como `unknown` y resolverlo después por runtime/configuración.
- Source/log scanners sólo leen roots/providers resueltos y validados; nunca hacen un scan global del host.
- Los tests del instalador deben incluir al menos un layout convencional y otro con nombres/rutas no convencionales.
- `InstanceProfile`/capabilities deben distinguir `DETECTED`, `NOT_FOUND`, `NO_PERMISSION` y `ERROR` en vez de inferir una única instalación esperada.

## Estado actual de M1

El bootstrap expone overrides para config Odoo, service/user, addons roots, `data_dir`, log file, directorios propios, puerto local, nombre de Assistant DB y ruta de Alembic. Las rutas comunes y nombres `odoo*.service` se usan sólo para autodetección; un unit explícito puede tener cualquier nombre.

Los futuros M1/M3/M7 deben mantener esta política al añadir PostgreSQL bootstrap, systemd, Settings, source y logs.

## Estado actual de M2

El Assistant Service resuelve la URL base para sus callbacks acotados hacia
Odoo mediante el override explícito `ODOO_AI_ODOO_BASE_URL`. No existe un
default de host o puerto. El adapter valida `http`/`https`, host y puerto, y
rechaza credentials, path, query y fragmento para que las únicas rutas posibles
sean los dos handlers internos fijos. La futura superficie de Settings podrá
administrar este dato server-side sin cambiar el port ni aceptar valores desde
JS o prompts.

## Estado actual de M6

La autoridad de commit ACTION no reutiliza los tokens `v1`, `q1` o `p1`.
`ODOO_AI_ACTION_AUTHORITY_SECRET_FILE` es un override explícito obligatorio en
el Assistant Service y en el proceso Odoo para habilitar `a1`. No tiene ruta
default: si falta, no es un fichero regular, supera 4096 bytes, tiene permisos
para `other` o contiene menos de 43 bytes, ACTION queda degradado y no ejecuta
writes. La provisión/rotación host-level de este segundo secret queda en el
setup boundary; Odoo Settings no debe leer ni devolver su contenido.

## Contrato de configuración M7

M7 usa un catálogo versionado único para distinguir tres clases de datos:

- `HOST_ONLY`: bootstrap/supervisor conserva la autoridad. Odoo Settings sólo
  puede mostrar un estado saneado o la razón por la que el valor es de sólo
  lectura.
- `ADMIN_MUTABLE`: un administrador de sistema de Odoo puede solicitar un
  override acotado que tenga un consumidor real.
- `DISCOVERED`: hechos observados por Odoo/runtime; no son una concesión de
  privilegios sobre el host.

La provenance efectiva mantiene el orden `explicit_override > runtime >
supervisor > config > hint > unknown`. `unknown` es distinto de un valor
conocido pero vacío. Los snapshots se ordenan por key y llevan fingerprint
determinista.

| Key estable | Ownership | Fuente/límite | Aplicación |
| --- | --- | --- | --- |
| `connection.service_url` | ADMIN_MUTABLE (Odoo) | sólo HTTP loopback validado | hot |
| `connection.machine_credential` | HOST_ONLY | referencia provisionada por setup; sólo se expone `configured` | setup |
| `host.bind_host`, `host.bind_port` | HOST_ONLY | env/systemd | setup |
| `host.database_url` | HOST_ONLY | env root-owned; siempre redactado | setup |
| `host.runtime_root`, `host.service_unit` | HOST_ONLY | bootstrap/supervisor | setup |
| `source.authorized_roots` | HOST_ONLY | `ODOO_AI_SOURCE_ROOTS` materializado por bootstrap | setup |
| `source.selected_roots` | ADMIN_MUTABLE | subconjunto/descendiente validado de `source.authorized_roots` | hot |
| `logs.authorized_file`, `logs.authorized_unit` | HOST_ONLY | `ODOO_AI_LOG_FILE` / `ODOO_AI_JOURNAL_UNIT` | setup |
| `logs.provider` | ADMIN_MUTABLE | sólo `auto`, `file` o `journal` si existe candidato host | hot |
| `reasoning.executable`, `reasoning.home` | HOST_ONLY | env/bootstrap | setup |
| `reasoning.model` | ADMIN_MUTABLE | modelo acotado para el runtime Codex | hot |
| `reasoning.startup_timeout_seconds` | ADMIN_MUTABLE | `1..120` s | hot |
| `reasoning.turn_timeout_seconds` | ADMIN_MUTABLE | `5..600` s | hot |
| `knowledge.provider` | DISCOVERED | índice PostgreSQL ya provisionado por M5 | read-only |
| `odoo.version`, `odoo.database`, `odoo.addons_roots` | DISCOVERED | runtime Odoo autenticado | read-only |

Los paths físicos del host son información administrativa: no se envían al
ReasoningEngine ni a usuarios no administradores. Un selector mutable nunca
crea su propia allowlist; primero se canonicaliza y después se comprueba contra
la envelope HOST_ONLY, incluyendo escapes mediante symlink.

No existe ninguna key M7 para ampliar handlers/capabilities ACTION. Los límites
de M6 siguen siendo código/política curada y no configuración administrativa.

### Aplicación runtime M7-03

El Assistant expone únicamente una API interna machine-auth para configuración:

- `GET /v1/admin/configuration`: snapshot saneado, revision, fingerprint,
  provenance y opciones autorizadas;
- `POST /v1/admin/configuration/validate`: valida el contrato cerrado sin
  persistir ni activar;
- `POST /v1/admin/configuration/apply`: exige `expected_revision`, revalida
  envelopes/providers y sólo entonces avanza el estado.

La Assistant DB mantiene un singleton de estado y un historial append-only de
revisiones válidas. La revisión `0` significa que no existe overlay persistido.
Cada apply real bloquea el estado, comprueba la revisión esperada, inserta la
nueva revisión y mueve el puntero dentro de la misma transacción. Una petición
inválida o stale no modifica el último estado válido. El audit guarda actor,
revision, fingerprint y **keys cambiadas**, nunca valores de configuración ni
secretos.

Los consumers runtime no modifican `os.environ`: source, selección de provider
de logs y settings Codex superponen sólo las keys `ADMIN_MUTABLE` registradas.
Executable/home/CWD/sandbox, roots autorizados, fichero/unit de logs, database,
secrets y supervisor continúan siendo host-owned. Un cambio de revision invalida
las caches compatibles; `restart_required` y `setup_required` son estados
representables pero M7 no ejecuta restart/systemd/setup desde Odoo.

La readiness administrativa incluye ahora el estado `configuration`. Una
configuración persistida que deje de cumplir los límites HOST_ONLY actuales
queda `ERROR`/fail-closed; restaurar el boundary válido permite volver a usar la
misma última revisión sin haberla destruido.

**Estado:** M7-01, M7-02 y M7-03 implementados en `main`; verificación runtime,
pytest, Ruff, mypy, migración PostgreSQL real y addon Odoo pendiente. Esto no
marca M7 como PASS ni inicia M7-04.

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

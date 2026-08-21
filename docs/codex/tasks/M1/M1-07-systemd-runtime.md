# M1-07 — systemd y lifecycle del runtime

## Contexto

- Requiere M1-06 completado y verde.
- El Assistant Service debe ejecutarse localmente sin root y escuchar sólo en loopback para el MVP.
- systemd es el supervisor del **Assistant Service** en el perfil inicial; no implica que Odoo tenga que usar systemd.
- `docs/DEPLOYMENT_CONFIG.md` define la política de deployment adaptable.

## Objetivo

Instalar y operar el Assistant Service mediante systemd de forma idempotente, usando el usuario/config/secreto creados por bootstrap y manteniendo un lifecycle observable y seguro sin acoplar Odoo a un nombre de unit o supervisor concretos.

## Contratos que NO puedes romper

- runtime FastAPI y config existentes;
- bootstrap y credenciales de M1-05/M1-06;
- `/health` y `/v1/admin/status`;
- Odoo deployment facts/overrides resueltos por M1-05.

## Debes implementar

- unit del Assistant bajo `installer/systemd/`;
- instalación/actualización idempotente de la unit desde bootstrap;
- ejecución como usuario de servicio no-root;
- bind del service a loopback usando host/port configurados;
- carga de config/secreto sin exponerlos en command line;
- restart policy razonable y logging compatible con journal;
- `daemon-reload`, enable/start/restart sólo cuando corresponda;
- smoke checks con systemd y endpoints;
- paths de config/state/runtime procedentes de BootstrapPaths/configuración, no repetidos como constantes dentro de la unit/template;
- unit name del Assistant configurable si existe una necesidad operativa real, o al menos centralizado en un único setting/template y no repartido por código.

Aplica hardening de systemd sólo cuando sea compatible con las necesidades reales del runtime. Evita una lista especulativa de restricciones que después bloquee source/log providers; cualquier hardening relevante debe estar justificado y testeado.

## Odoo supervisor

- No exigir `odoo.service` ni `odoo*.service` como contrato.
- Si Odoo usa systemd, aprovechar el unit detectado/indicado para metadata y posteriormente JournalLogProvider.
- Si Odoo usa otro supervisor o se arranca de otra forma, el Assistant Service puede seguir usando systemd; el bootstrap debe trabajar con usuario/paths explícitos o facts resueltos sin inventar una unit.
- No introducir dependencia application → systemd.

## Fuera de scope

- JournalLogProvider como tool del agente;
- scanner/source access;
- Codex sandbox;
- packaging `.deb` completo;
- implementar supervisores alternativos para el Assistant Service;
- alta disponibilidad/multi-instance.

## Restricciones

- proceso runtime nunca como root;
- no `0.0.0.0` por defecto ni como shortcut para resolver conectividad del MVP;
- secretos no aparecen en unit pública, `ps`, Git ni logs;
- bootstrap puede usar privilegios; el service no los conserva;
- no hardcodear paths de cliente en unit/templates;
- no condicionar el arranque del Assistant a que Odoo tenga un unit systemd con nombre convencional.

## Tests obligatorios

En un host con systemd real:

- instalar unit;
- `systemctl is-active`;
- verificar usuario efectivo del proceso;
- verificar socket/listen sólo loopback y puerto configurado;
- `curl` `/health` y `/v1/admin/status`;
- repetir bootstrap/update y confirmar idempotencia;
- reinicio del service;
- configuración con directorios/puerto no-default;
- fixture/preflight de Odoo sin unit systemd pero con usuario explícito;
- suite/lint/type-check.

## Acceptance criteria

- service arranca automáticamente mediante systemd en el perfil soportado;
- proceso corre como usuario no-root;
- sólo escucha en loopback;
- endpoints responden tras restart;
- segunda instalación no crea units/config duplicadas ni falla;
- no se exponen secretos;
- paths/puerto del Assistant se renderizan desde configuración central, no desde constantes duplicadas;
- Odoo puede tener nombre de unit arbitrario o no usar systemd sin invalidar por ello el deployment;
- tests verdes.

## Antes de editar

1. Comprueba si el host actual usa systemd y cómo corre Odoo; no asumas que ambas cosas coinciden.
2. Resume unit/config propuesta y de dónde sale cada path/parámetro.
3. Señala cualquier limitación específica del entorno de desarrollo.

## Después

1. Ejecuta smoke real si el host lo permite.
2. Informa `systemctl`/socket/health de forma sanitizada.
3. Lista assumptions de supervisor que permanezcan y justifica si pertenecen al Assistant profile o a Odoo.
4. No avances a M1-08.

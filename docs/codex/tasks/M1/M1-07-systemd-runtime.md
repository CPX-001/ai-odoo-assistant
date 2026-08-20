# M1-07 — systemd y lifecycle del runtime

## Contexto

- Requiere M1-06 completado y verde.
- El service debe ejecutarse localmente sin root y escuchar sólo en loopback para el MVP.

## Objetivo

Instalar y operar el Assistant Service mediante systemd de forma idempotente, usando el usuario/config/secreto creados por bootstrap y manteniendo un lifecycle observable y seguro.

## Contratos que NO puedes romper

- runtime FastAPI y config existentes;
- bootstrap y credenciales de M1-05/M1-06;
- `/health` y `/v1/admin/status`.

## Debes implementar

- unit bajo `installer/systemd/`;
- instalación/actualización idempotente de la unit desde bootstrap;
- ejecución como usuario de servicio no-root;
- bind del service a `127.0.0.1`;
- carga de config/secreto sin exponerlos en command line;
- restart policy razonable y logging compatible con journal;
- `daemon-reload`, enable/start/restart sólo cuando corresponda;
- smoke checks con systemd y endpoints.

Aplica hardening de systemd sólo cuando sea compatible con las necesidades reales del runtime. Evita una lista especulativa de restricciones que después bloquee source/log providers; cualquier hardening relevante debe estar justificado y testeado.

## Fuera de scope

- JournalLogProvider como tool del agente;
- scanner/source access;
- Codex sandbox;
- packaging `.deb` completo;
- alta disponibilidad/multi-instance.

## Restricciones

- proceso runtime nunca como root;
- no `0.0.0.0` por defecto;
- secretos no aparecen en unit pública, `ps`, Git ni logs;
- bootstrap puede usar privilegios; el service no los conserva.

## Tests obligatorios

En un host con systemd real (WSL sólo si systemd está plenamente habilitado):

- instalar unit;
- `systemctl is-active`;
- verificar usuario efectivo del proceso;
- verificar socket/listen sólo loopback;
- `curl` `/health` y `/v1/admin/status`;
- repetir bootstrap/update y confirmar idempotencia;
- reinicio del service;
- suite/lint/type-check.

## Acceptance criteria

- service arranca automáticamente mediante systemd;
- proceso corre como usuario no-root;
- sólo escucha en loopback;
- endpoints responden tras restart;
- segunda instalación no crea units/config duplicadas ni falla;
- no se exponen secretos;
- tests verdes.

## Antes de editar

1. Comprueba si el host actual usa systemd y cómo corre Odoo; no asumas.
2. Resume unit/config propuesta.
3. Señala cualquier limitación específica de WSL.

## Después

1. Ejecuta smoke real si el host lo permite.
2. Informa `systemctl`/socket/health de forma sanitizada.
3. Si WSL no equivale a un host soportado, deja constancia para M1-10.
4. No avances a M1-08.

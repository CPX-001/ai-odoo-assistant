# M1-05 — Bootstrap foundation del host

## Contexto

- Requiere M1-04 completado y verde.
- El escenario soportado inicial es Odoo 18 Community, Linux self-hosted, PostgreSQL.
- El bootstrap es el único paso privilegiado normal; Odoo no debe conservar root.
- `docs/DEPLOYMENT_CONFIG.md` define la política de autodetección y overrides.

## Objetivo

Crear la base idempotente del instalador/bootstrap para detectar el deployment y preparar usuario, directorios, configuración y secreto compartido del Assistant Service sin configurar todavía PostgreSQL ni systemd.

El entorno DEV no es el modelo del cliente: rutas y nombres convencionales son hints, no contratos.

## Contratos que NO puedes romper

- runtime/config de M1-01..04;
- `installer/AGENTS.md`;
- `docs/DEPLOYMENT_CONFIG.md`;
- separación addon/service y secreto fuera de prompts/repo.

## Debes implementar

- entrypoint del bootstrap bajo `installer/bootstrap/`;
- preflight/detección del Linux soportado;
- detección **o parámetro explícito** de config Odoo; la ausencia de un `odoo.conf` convencional no debe implicar por sí sola que el deployment sea inválido;
- lectura segura de hints disponibles (`addons_path`, `data_dir`, logfile y datos PostgreSQL no secretos) sin exigir que todas esas opciones existan;
- overrides explícitos para paths relevantes que no puedan autodetectarse de forma fiable;
- detección del servicio Odoo cuando sea posible;
- soporte de nombres explícitos de servicio arbitrarios: no exigir prefijo `odoo`;
- posibilidad de continuar con usuario Odoo explícito cuando Odoo no use systemd;
- creación idempotente del usuario/grupo de servicio y directorios runtime necesarios;
- directorios propios del Assistant configurables por parámetros, con defaults razonables;
- generación/instalación de service config no secreta;
- puerto/nombre de Assistant DB/ruta de Alembic configurables sin editar código; bind restringido a loopback por seguridad del MVP;
- generación de shared secret fuera del repo con permisos restrictivos;
- modo de salida/diagnóstico claro cuando algo no pueda autodetectarse;
- tests unitarios de parsing/preflight y smoke en el host DEV cuando sea seguro.

## Fuera de scope

- crear DB/role PostgreSQL (M1-06);
- unit systemd del Assistant (M1-07);
- copiar/instalar addon funcional (M1-08);
- paquete `.deb` completo;
- implementar adapters completos Docker/Odoo.sh/supervisord;
- Codex/source/log permissions.

Fuera de scope no significa hardcodear esos casos como imposibles. Cuando no se soporten aún, conservar boundaries/overrides que permitan añadir un provider/adapter posterior.

## Restricciones

- no modificar `odoo.conf` salvo necesidad explícita y verificada;
- no guardar secretos en Git, stdout detallado, logs o argumentos de proceso si puede evitarse;
- una segunda ejecución debe reutilizar recursos válidos y corregir sólo drift seguro;
- nunca dar root permanente al proceso Odoo o al Assistant Service;
- si la detección es ambigua, fallar con una excepción accionable en vez de adivinar;
- no convertir `/etc/odoo*.conf`, `odoo*.service`, usuario `odoo`, `/var/log/odoo` o `/opt/odoo` en requisitos;
- no rechazar una config Odoo sólo porque no tenga `addons_path`/logfile/data_dir: esos valores pueden quedar `unknown` y resolverse después;
- no introducir paths de cliente en application code.

## Tests obligatorios

- parsing de configuración convencional;
- config en ruta/nombre arbitrario;
- config sin opciones opcionales;
- paths con espacios cuando sean técnicamente válidos;
- nombre explícito de systemd unit no relacionado con `odoo`;
- Odoo sin systemd + usuario explícito;
- múltiples configs/services detectados -> ambigüedad accionable;
- primera ejecución en entorno temporal/fixture;
- segunda ejecución idempotente;
- permisos/propietario del secreto y directorios cuando el host permita comprobarlos;
- suite, lint/type-check/shell lint si se introduce shell.

## Acceptance criteria

- bootstrap descubre o recibe explícitamente los datos mínimos del deployment;
- los defaults de paths/nombres sólo aceleran autodetección y pueden ser sustituidos sin tocar código;
- crea usuario/directorios/config/secreto de forma repetible;
- no requiere root permanente después del bootstrap;
- no altera Odoo innecesariamente;
- fallos de detección producen instrucciones claras;
- un layout de cliente no convencional cubierto por fixture supera el preflight;
- tests verdes.

## Antes de editar

1. Inspecciona el host sólo con comandos de lectura primero.
2. Resume qué detectaste, su procedencia y qué partes necesitan parámetros.
3. Distingue defaults/hints de requisitos reales.
4. Explica el mecanismo de idempotencia propuesto.

## Después

1. Ejecuta tests y smoke seguro.
2. Informa cambios host realizados y cómo revertirlos.
3. Lista cualquier assumption de deployment que haya quedado en código y justifica por qué es una restricción del perfil soportado y no una comodidad del DEV.
4. No avances a M1-06.

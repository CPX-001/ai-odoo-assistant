# M1-05 — Bootstrap foundation del host

## Contexto

- Requiere M1-04 completado y verde.
- El escenario soportado inicial es Odoo 18 Community, Linux self-hosted, PostgreSQL.
- El bootstrap es el único paso privilegiado normal; Odoo no debe conservar root.

## Objetivo

Crear la base idempotente del instalador/bootstrap para detectar el deployment y preparar usuario, directorios, configuración y secreto compartido del Assistant Service sin configurar todavía PostgreSQL ni systemd.

## Contratos que NO puedes romper

- runtime/config de M1-01..04;
- `installer/AGENTS.md`;
- separación addon/service y secreto fuera de prompts/repo.

## Debes implementar

- entrypoint del bootstrap bajo `installer/bootstrap/`;
- preflight/detección de Linux soportado;
- detección o parámetro explícito de `odoo.conf`;
- extracción segura de `addons_path` y datos necesarios para localizar Odoo/PostgreSQL sin ejecutar código arbitrario;
- detección del servicio Odoo cuando sea posible;
- creación idempotente del usuario/grupo de servicio y directorios runtime necesarios;
- generación/instalación de service config no secreta;
- generación de shared secret fuera del repo con permisos restrictivos;
- modo de salida/diagnóstico claro cuando algo no pueda autodetectarse;
- tests unitarios de parsing/preflight y smoke en el host DEV cuando sea seguro.

## Fuera de scope

- crear DB/role PostgreSQL (M1-06);
- unit systemd (M1-07);
- copiar/instalar addon funcional (M1-08);
- paquete `.deb` completo;
- Docker/Odoo.sh/hosting adapters;
- Codex/source/log permissions.

## Restricciones

- no modificar `odoo.conf` salvo necesidad explícita y verificada;
- no guardar secretos en Git, stdout detallado, logs o argumentos de proceso si puede evitarse;
- una segunda ejecución debe reutilizar recursos válidos y corregir sólo drift seguro;
- nunca dar root permanente al proceso Odoo o al Assistant Service;
- si la detección es ambigua, fallar con una excepción accionable en vez de adivinar.

## Tests obligatorios

- parsing de configuraciones fixture;
- primera ejecución en entorno temporal/fixture;
- segunda ejecución idempotente;
- permisos/propietario del secreto y directorios cuando el host permita comprobarlos;
- suite, lint/type-check/shell lint si se introduce shell.

## Acceptance criteria

- bootstrap descubre o recibe explícitamente los datos mínimos del deployment;
- crea usuario/directorios/config/secreto de forma repetible;
- no requiere root permanente después del bootstrap;
- no altera Odoo innecesariamente;
- fallos de detección producen instrucciones claras;
- tests verdes.

## Antes de editar

1. Inspecciona el WSL/host sólo con comandos de lectura primero.
2. Resume qué detectaste y qué partes necesitan parámetros.
3. Explica el mecanismo de idempotencia propuesto.

## Después

1. Ejecuta tests y smoke seguro.
2. Informa cambios host realizados y cómo revertirlos.
3. No avances a M1-06.

# M5-09 — E2E real QUERY + HOW_TO con Codex

## Contexto

- Requiere M5-01..M5-08 verdes.
- Un fake engine no basta para demostrar el objetivo observable del milestone.
- El runner debe ser desechable y no depender de datos privados del entorno DEV.

## Objetivo

Demostrar dos flujos reales completos en Odoo 18 Community con Chromium, Assistant Service y Codex autenticado: un QUERY de negocio bajo permisos reales y un HOW_TO adaptado a navegación/schema/knowledge de una instalación fixture.

## Fixture E2E

Crea/reutiliza un addon de test mínimo y determinista, sin convertirlo en código de producto, que permita preparar:

### Caso QUERY

- usuario A con acceso a un conjunto conocido de registros;
- al menos un registro que debe quedar oculto por record rule/compañía/ACL al usuario A;
- campos y valores conocidos para ejecutar una búsqueda o aggregate con resultado exacto;
- usuario B o contexto negativo para demostrar que el resultado cambia según permisos.

La pregunta debe ser natural y comprobar contenido semántico, no una frase exacta del LLM. Ejemplo admisible: cuántos/qué pedidos abiertos pertenecen a un cliente fixture, siempre que el resultado esperado sea determinista.

### Caso HOW_TO

- menú/action/model fixture visible para el usuario A y, si es útil, uno oculto;
- documento knowledge fixture que explique una operación concreta de ese módulo;
- schema runtime que permita comprobar campos reales;
- pregunta natural cuyo camino correcto requiera combinar navegación + schema + documento.

No dependas de una ruta nativa de menú cuyo nombre/estructura pueda variar si un fixture propio prueba mejor el contrato.

## Runner real

El runner debe levantar/preparar de forma reproducible:

- PostgreSQL/Odoo 18 fixture;
- addon Assistant actualizado;
- Assistant DB/migraciones;
- knowledge root/documentos temporales;
- source/log state requerido por readiness existente;
- Assistant Service;
- Codex App Server real bajo usuario no-root;
- Chromium/browser test.

Al finalizar elimina procesos, DBs/roles, fixtures y directorios temporales que haya creado.

## Verificaciones QUERY

- browser → Odoo únicamente;
- identidad real del usuario A llega server-side;
- Codex solicita al menos una QUERY tool real;
- schema efectivo limita fields;
- resultado exacto coincide con fixture;
- registro prohibido no aparece ni en answer, tool output browser-facing, citations o traces;
- aggregate/count, si se usa, coincide exactamente;
- citas apuntan a Evidence checked del turn;
- misma pregunta con usuario/contexto restringido respeta sus permisos.

## Verificaciones HOW_TO

- Codex usa al menos una knowledge tool real;
- navegación citada existe y es visible para el usuario;
- schema/campo citado existe cuando la respuesta lo menciona;
- excerpt documental tiene fingerprint vigente;
- la guía es útil y causalmente consistente con el fixture;
- menú oculto no se presenta como ruta disponible;
- al alterar/retirar el documento, no sobrevive una cita stale de alta confianza.

## Negativos mínimos

- Codex executable ausente → error controlado/degraded sin detener Odoo;
- query fuera de scope → rechazado;
- document fingerprint stale → no Evidence checked;
- usuario sin acceso → no fuga de existencia/datos;
- canary de secret ausente en browser/traces;
- no capacidad write/action disponible.

## Tests/artefactos requeridos

- runner reproducible bajo `tests/e2e/`;
- reporte `docs/codex/M5_E2E_REPORT.md` con datos fixture, tools realmente usadas y resultados, sin secretos/physical paths;
- suite y checks relevantes tras el runner.

## Acceptance criteria

- existe un QUERY real útil con Codex y Odoo real bajo ACL/record rules;
- existe un HOW_TO real que usa knowledge + facts de la instalación;
- ambos pasan por browser → Odoo → Assistant → Codex/tools → Evidence → respuesta;
- no se infiere PASS desde mocks;
- no hay capacidades M6.

## Después

1. Registra tools y Evidence observadas, no el reasoning interno de Codex.
2. Incluye los negativos y cleanup en el reporte.
3. No avances a M5-10 si cualquier verificación real relevante falta.

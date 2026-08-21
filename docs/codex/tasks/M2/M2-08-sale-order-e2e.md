# M2-08 — Vertical slice E2E desde sale.order

## Contexto

- Requiere M2-07 verde.
- Esta task integra lo ya implementado; no debe introducir arquitectura nueva salvo fixes estrictamente necesarios.
- El objetivo observable de M2 es preguntar desde un pedido y releerlo como el usuario real.

## Objetivo

Demostrar en Odoo 18 Community + Assistant Service reales que un usuario abre un `sale.order`, abre el asistente, envía una pregunta contextual y recibe una respuesta determinista basada en una relectura ORM del pedido bajo sus permisos efectivos.

## Flujo obligatorio

El smoke/E2E debe evidenciar:

1. usuario interno autenticado abre una form `sale.order` real;
2. panel del asistente captura `model="sale.order"` y el `res_id` correcto;
3. usuario escribe una pregunta de prueba, por ejemplo `¿Qué pedido estoy viendo?`;
4. browser envía sólo mensaje + `ScreenContext` a Odoo;
5. Odoo deriva identidad efectiva y crea delegación server-side;
6. Odoo server llama al Assistant Service autenticado;
7. Assistant Service llama a `OdooGateway` con la delegación;
8. Odoo revalida delegación y relee el pedido por ORM como el usuario;
9. service devuelve una respuesta context-read bounded;
10. UI muestra al menos el `display_name`/identificador visible y, si está disponible, estado del pedido;
11. ningún dato de negocio proviene de un `display_name`/field confiado desde JS.

## Debes reutilizar

- addon/panel M2-06;
- security M2-07;
- service context-read M2-05;
- adapter M2-04;
- runtime/installer M1;
- `sale` sólo como fixture de aceptación, no como dependencia arquitectónica del addon.

## Debes implementar

### 1. Fixture real

Crear de forma reproducible:

- partner mínimo;
- pedido de venta;
- usuario no-admin con permisos suficientes;
- opcionalmente segundo usuario que no pueda acceder al pedido para el caso negativo.

### 2. Browser/integration path

Preferir `HttpCase`, web tour/HOOT o mecanismo soportado por Odoo 18 que pruebe realmente assets + web client. Si el entorno impide browser automation fiable, mantener además un smoke server-side reproducible, pero no declarar PASS de M2 sin alguna evidencia de que el panel/captura de contexto funciona en el cliente web real.

### 3. Assistant Service real

Usar proceso HTTP real del service, no un fake in-process para el acceptance principal. Puede ejecutarse mediante el perfil M1 disponible o un proceso disposable equivalente. Debe usar el adapter HTTP real hacia Odoo.

### 4. Caso negativo

Demostrar al menos uno:

- usuario sin acceso al pedido recibe deny controlado; o
- ScreenContext manipulado para otro pedido fuera del scope no devuelve sus datos.

Idealmente ambos si el fixture lo permite sin ampliar mucho el test.

## Fuera de scope

- respuesta inteligente/LLM;
- source/logs;
- query libre;
- writes;
- streaming/history.

## Restricciones

- no mockear la relectura en el acceptance principal;
- no usar admin para ocultar problemas de permisos;
- no añadir `sudo()` al fixture productivo;
- no hardcodear un pedido/DB/path del DEV;
- no hacer que el addon dependa de `sale` fuera del test/smoke.

## Tests obligatorios

- E2E positivo completo;
- caso negativo de permisos/scope;
- addon install/upgrade;
- service health/status sigue correcto;
- browser no llama al Assistant Service directamente;
- token/secret no aparece en browser/network payload de respuesta;
- suite/lint/type-check.

## Acceptance criteria

- el vertical slice completo funciona con Odoo y service reales;
- el pedido mostrado procede de relectura ORM bajo usuario real;
- modificar hints del browser no sustituye la relectura;
- permisos denegados se respetan;
- no existe Codex/ReasoningEngine todavía;
- tests verdes.

## Antes de editar

1. Describe el fixture exacto y cómo arrancarás Odoo/service.
2. Define la evidencia observable del browser test.
3. No rediseñes M2 si un smoke puede usar las piezas existentes.

## Después

1. Informa comandos reproducibles.
2. Adjunta/resume evidencia del caso positivo y negativo.
3. Lista cualquier fix necesario para hacer funcionar el flujo real.
4. No avances a M2-09.

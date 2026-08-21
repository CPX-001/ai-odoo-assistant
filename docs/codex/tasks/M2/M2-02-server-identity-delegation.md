# M2-02 — Identidad efectiva y emisión server-side de delegación

## Contexto

- Requiere M2-01 verde.
- El browser sólo puede aportar `ScreenContext` y texto; toda identidad debe derivarse dentro de Odoo.
- La delegación creada en M2-01 todavía no autoriza ninguna lectura hasta que M2-03 implemente los tools.

## Objetivo

Implementar en el addon la preparación server-side de un turn contextual: validar el `ScreenContext`, derivar la identidad efectiva Odoo y emitir una delegación firmada, corta y scoped al registro/modelo actual, sin devolver nunca el token al browser.

## Contratos que NO puedes romper

- `ScreenContext` existente;
- `UserExecutionContext` existente;
- codec/claims de M2-01;
- current-user semantics de `addons/AGENTS.md`;
- browser → Odoo → Assistant Service boundary.

## Debes reutilizar

- addon/config y `AssistantServiceClient` de M1;
- Odoo `request.env`/environment actual para identidad y compañías;
- contracts M0/M2 en el lado del service, sin copiar identidad desde JS.

## Debes implementar

### 1. Validación server-side de ScreenContext

Crear una función/model service estrecho que acepte el payload de navegación y:

- ignore/rechace cualquier clave de identidad inesperada;
- valide model name, IDs positivos, tamaño de `selected_ids`, `view_type`, timestamps y tamaños;
- mantenga `action_id`, `menu_id` y `allowed_context_subset` como hints, nunca como authority;
- aplique una whitelist pequeña al `allowed_context_subset`; no reenviar el contexto completo de Odoo/JS;
- para M2, priorice un único `res_id` actual. Soporte de selección masiva sólo si queda igualmente bounded y probado.

### 2. Derivar UserExecutionContext

Desde el env Odoo autenticado, no desde parámetros del cliente:

- `uid` efectivo;
- compañía efectiva;
- compañías permitidas realmente activas/autorizadas;
- lenguaje efectivo.

La lista de compañías no puede ampliarse con valores enviados por el browser. Usa APIs Odoo 18 que respeten la selección actual y valida cualquier contexto multi-company contra las compañías del usuario.

### 3. Scope de delegación

Emitir una delegación para el turn que quede ligada como mínimo a:

- `turn_id` generado server-side;
- identidad efectiva;
- DB/instancia actual según el contrato M2-01;
- modelo actual;
- `res_id` actual o conjunto mínimo permitido;
- scopes de sólo metadata/read necesarios para M2;
- expiración corta.

No emitir scopes globales de modelo, search arbitrario ni method execution.

### 4. Encapsulación del token

El helper que prepara el turn puede entregar el token únicamente a código server-side que vaya a llamar al Assistant Service. La respuesta RPC/JSON que finalmente vea el browser nunca debe incluir:

- token;
- firma;
- shared secret;
- internal Assistant URL;
- headers de autenticación.

## Fuera de scope

- endpoint callback service → Odoo;
- lectura ORM;
- adapter `OdooGateway`;
- endpoint de turn del Assistant Service;
- panel OWL;
- history/persistencia de chat;
- Codex/writes.

## Restricciones

- no `sudo()` para derivar identidad;
- no confiar en `uid`, company ids o lang enviados desde frontend;
- no autorizar un modelo/ID sólo porque aparezca en ScreenContext;
- no ampliar scope a todos los registros del modelo;
- no guardar tokens completos en DB/logs.

## Tests obligatorios

Tests Odoo 18 para:

- usuario A produce `uid=A` aunque el payload intente enviar otro uid;
- compañía efectiva y allowed companies coinciden con el env real;
- intento de incluir compañía no autorizada no amplía el contexto;
- `res_id`/modelo inválidos se rechazan antes de firmar;
- delegación contiene turn/model/id/scopes esperados y TTL correcto;
- token no aparece en payload destinado al browser ni en excepciones;
- `selected_ids` y context subset respetan límites;
- suite Python existente, tests Odoo aplicables, lint/type-check.

## Acceptance criteria

- Odoo puede construir un turn contextual sin confiar en identidad de JS;
- delegación queda ligada al usuario/compañías/registro real del turn;
- el token permanece exclusivamente server-side;
- no existe todavía ninguna lectura Odoo ejecutable por el Assistant Service;
- tests verdes.

## Antes de editar

1. Inspecciona cómo Odoo 18 expone usuario/companies/context en el addon real.
2. Resume qué partes del `ScreenContext` serán hints y cuáles entran en el scope firmado.
3. Si necesitas cambiar claims de M2-01, justifica el cambio y actualiza tests de contrato.

## Después

1. Ejecuta tests.
2. Informa el mapping exacto Odoo env → `UserExecutionContext`.
3. Demuestra que un uid/company falsos del browser no cambian la delegación.
4. No avances a M2-03.

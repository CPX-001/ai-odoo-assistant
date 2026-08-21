# M2-06 — Panel Odoo-native y captura de ScreenContext

## Contexto

- Requiere M2-05 verde.
- Hasta ahora el addon sólo tiene Diagnostics de M1; esta task añade la primera UX de usuario.
- El browser debe hablar exclusivamente con Odoo. Odoo server prepara identidad/delegación y llama al Assistant Service.

## Objetivo

Crear una UI Odoo 18 Community mínima y usable —systray/panel lateral o patrón nativo equivalente— que capture el `ScreenContext` del registro actual, envíe una pregunta al backend Odoo y muestre la respuesta context-read de M2 sin exponer identidad, secrets, token ni URL interna.

## Contratos que NO puedes romper

- `ScreenContext` M0;
- server identity/delegation M2-02;
- context-read API M2-05;
- browser → Odoo → Assistant Service;
- UX Odoo-native de `addons/AGENTS.md`.

## Debes reutilizar

- servicios/router/action state nativos de Odoo 18 para conocer pantalla actual;
- `AssistantServiceClient` server-side de M1, ampliándolo de forma estrecha para POST context-read;
- mecanismos RPC/model/controller Odoo existentes;
- assets OWL del módulo `web`.

## Debes implementar

### 1. Entrada global y panel

- añadir dependencia/assets necesarios del módulo `web`;
- entrada de systray o mecanismo Odoo-native disponible globalmente;
- panel/drawer/dialog no intrusivo con:
  - contexto actual visible de forma resumida;
  - input de pregunta;
  - botón enviar;
  - loading;
  - error sanitizado;
  - respuesta context-read.

No intentar construir todavía un chat completo con streaming, markdown avanzado, history o attachments.

### 2. Captura de ScreenContext

Usar servicios Odoo/web client antes que DOM scraping o parsing frágil de URL. Capturar cuando estén disponibles:

- action id;
- menu id;
- view type;
- model;
- res id;
- selected ids bounded;
- subset whitelisted de contexto;
- timestamp.

Nunca añadir `uid`, groups, company ids confiados, session id, cookies ni access tokens.

En una form de `sale.order`, `model` y `res_id` deben identificar el pedido realmente abierto. Si la pantalla no tiene un registro útil, el panel debe explicar que no hay contexto de registro para M2 en lugar de inventarlo.

### 3. Bridge browser → Odoo server

Crear/usar un método/controller autenticado por la sesión normal del usuario que:

1. recibe sólo texto + ScreenContext;
2. deriva identidad y delegación mediante M2-02;
3. llama al Assistant Service server-side con `AssistantServiceClient`;
4. devuelve al browser únicamente la respuesta sanitizada.

El token de delegación se crea y consume en la capa server-side y **nunca forma parte de la respuesta RPC**.

### 4. UX mínima de contexto fresco

La UI debe distinguir claramente:

- contexto actual detectado;
- service unavailable/auth failure;
- permiso denegado al releer;
- éxito con registro releído.

No afirmar que el asistente “entiende” la pregunta todavía; M2 valida contexto y permisos.

## Fuera de scope

- conversation history persistente;
- streaming;
- source/log diagnostics en panel;
- Codex;
- acciones/writes;
- voice/files;
- compatibilidad Odoo 19.

## Restricciones

- no HTTP directo JS → Assistant Service;
- no internal URL/secret/token en JS bundle, DOM, localStorage o network response;
- no identidad confiada desde JS;
- no DOM scraping si Odoo expone estado mediante services;
- no dependencia de `sale` en el addon sólo por el smoke: la UI debe ser genérica.

## Tests obligatorios

- unit/QUnit/HOOT o mecanismo Odoo 18 apropiado para context capture;
- form view produce model/res_id correctos;
- list/no-record state se maneja sin inventar contexto;
- payload JS no contiene uid/company/secret/token;
- backend bridge deriva identidad real y llama al client server-side;
- service error → mensaje controlado;
- inspección/assets demuestra que no existe `fetch("http://127.0.0.1...`)` ni endpoint interno hardcodeado;
- instalación/upgrade del addon;
- suite/lint/type-check.

## Acceptance criteria

- usuario interno ve y abre el asistente desde Odoo;
- desde un registro puede enviar una pregunta;
- `ScreenContext` se captura con APIs Odoo-native;
- browser sólo habla con Odoo;
- respuesta procede de relectura server-side M2-05;
- ningún secreto/token/uid confiado cruza al frontend;
- addon sigue siendo genérico respecto a modelos;
- tests verdes.

## Antes de editar

1. Inspecciona APIs reales del web client Odoo 18 instalado; no asumas nombres de services por memoria.
2. Resume el componente/servicio nativo que usarás para obtener action/model/resId.
3. Señala cualquier asset/dependency nueva del manifest.

## Después

1. Actualiza/instala el addon en Odoo DEV.
2. Abre una form real y muestra evidencia del ScreenContext capturado.
3. Verifica en network/devtools que el browser sólo llama a Odoo.
4. No avances a M2-07.

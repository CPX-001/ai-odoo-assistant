# M1-08 — Addon placeholder y health visible desde Odoo

## Contexto

- Requiere M1-07 completado y verde.
- M1 necesita que Odoo detecte el Assistant Service, pero M2 implementará UI contextual, `ScreenContext`, delegación y ORM tools.
- Durante el MVP el browser habla con Odoo; Odoo server habla con el service local.

## Objetivo

Crear el addon Odoo 18 mínimo, instalable como módulo normal, capaz de comprobar server-side el health del Assistant Service y mostrar ese estado dentro de Odoo sin introducir todavía chat ni tools.

## Contratos que NO puedes romper

- `addons/AGENTS.md`;
- `/health` y `/v1/admin/status`;
- browser → Odoo → Assistant Service boundary;
- secreto/config runtime establecidos en M1.

## Debes implementar

- estructura mínima `addons/odoo_ai_assistant/` y `__manifest__.py`;
- módulo instalable en Odoo 18 Community;
- configuración server-side mínima para localizar/autenticar el Assistant Service según el mecanismo real ya creado;
- cliente HTTP Odoo→service estrecho para health/status, sin API genérica;
- una vista Odoo-native mínima en Settings/diagnóstico que permita ver/probar el estado del service;
- mensajes de error sanitizados y accionables;
- tests Odoo o smoke reproducible suficiente para demostrar instalación y health.

El shared secret no debe viajar al browser. Si `/health` es público sólo en loopback y `/v1/admin/status` requiere autenticación, respeta esa separación; no debilites endpoints para simplificar la UI.

## Fuera de scope

- systray/chat/panel contextual;
- `ScreenContext` runtime;
- signed delegation;
- `read_record`, `fields_get` o cualquier OdooGateway funcional;
- scanner/source/logs/Codex;
- writes/actions.

## Restricciones

- no `sudo()`;
- no SQL directo desde addon/service;
- identidad/config sensible siempre server-side;
- no llamadas browser directas a `127.0.0.1:<service>`;
- no `execute_kw`/método genérico;
- no guardar shared secret en campos visibles al usuario o en assets frontend.

## Tests obligatorios

- instalación/upgrade del addon en DB Odoo 18 DEV;
- health visible con service activo;
- estado de error claro con service detenido;
- comprobar que el browser no necesita conocer secreto/URL interna sensible;
- suite Python existente, lint/type-check y tests Odoo aplicables.

## Acceptance criteria

- addon se instala/actualiza como módulo Odoo normal;
- desde Odoo un administrador puede comprobar si el service está healthy;
- detener el service produce un diagnóstico controlado, no un traceback crudo;
- browser no habla directamente con Assistant Service;
- no se han adelantado features de M2;
- tests verdes.

## Antes de editar

1. Inspecciona la instalación Odoo real: addons_path, forma de arrancar tests y convenciones locales.
2. Resume la UI/config mínima propuesta.
3. Señala cualquier cambio necesario en el contrato HTTP antes de hacerlo.

## Después

1. Instala/actualiza el módulo en Odoo DEV.
2. Verifica estado con service activo y detenido.
3. Informa comandos y evidencia.
4. No avances a M1-09.

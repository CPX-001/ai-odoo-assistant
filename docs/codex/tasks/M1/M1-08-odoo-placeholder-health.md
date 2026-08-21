# M1-08 — Addon placeholder y health visible desde Odoo

## Contexto

- Requiere M1-07 completado y verde.
- M1 necesita que Odoo detecte el Assistant Service, pero M2 implementará UI contextual, `ScreenContext`, delegación y ORM tools.
- Durante el MVP el browser habla con Odoo; Odoo server habla con el service.
- `docs/DEPLOYMENT_CONFIG.md` exige que la configuración administrable no termine hardcodeada en addon/application.

## Objetivo

Crear el addon Odoo 18 mínimo, instalable como módulo normal, capaz de comprobar server-side el health del Assistant Service y mostrar ese estado dentro de Odoo sin introducir todavía chat ni tools.

La UI debe empezar a presentar deployment facts como datos configurados/detectados, no como constantes del entorno DEV.

## Contratos que NO puedes romper

- `addons/AGENTS.md`;
- `/health` y `/v1/admin/status`;
- browser → Odoo → Assistant Service boundary;
- secreto/config runtime establecidos en M1;
- política de overrides de `docs/DEPLOYMENT_CONFIG.md`.

## Debes implementar

- estructura mínima `addons/odoo_ai_assistant/` y `__manifest__.py`;
- módulo instalable en Odoo 18 Community;
- configuración server-side mínima para localizar/autenticar el Assistant Service según el mecanismo real ya creado, sin URL/puerto copiados en varios archivos;
- cliente HTTP Odoo→service estrecho para health/status, sin API genérica;
- una vista Odoo-native mínima en Settings/diagnóstico que permita ver/probar el estado del service;
- mostrar de forma sanitizada los deployment facts disponibles que sean útiles para diagnóstico (por ejemplo config path/service user/addons/log hint si ya existen en status), marcando desconocidos como tales;
- mensajes de error sanitizados y accionables;
- tests Odoo o smoke reproducible suficiente para demostrar instalación y health.

### Configuración administrable

M1-08 no necesita construir todavía todo el editor de source/logs de M3/M7, pero sí debe respetar estas reglas:

- ningún path del cliente se fija dentro del addon;
- los valores que el addon necesita se obtienen de Settings/config central;
- si se introduce un setting editable, debe persistirse como dato (Odoo/Assistant DB según boundary), no requerir editar Python/XML;
- los cambios que requieran privilegios del host no se ejecutan con root desde Odoo; se muestran como setup action/fallback controlado;
- preparar la UI/contratos para que M3/M7 puedan añadir overrides de source/logs sin rediseñar Settings.

El shared secret no debe viajar al browser. Si `/health` es público sólo en loopback y `/v1/admin/status` requiere autenticación, respeta esa separación; no debilites endpoints para simplificar la UI.

## Fuera de scope

- systray/chat/panel contextual;
- `ScreenContext` runtime;
- signed delegation;
- `read_record`, `fields_get` o cualquier OdooGateway funcional;
- scanner/source/logs/Codex;
- writes/actions;
- editor completo de todos los adapters/providers de deployment.

## Restricciones

- no `sudo()`;
- no SQL directo desde addon/service;
- identidad/config sensible siempre server-side;
- no llamadas browser directas a `127.0.0.1:<service>`;
- no `execute_kw`/método genérico;
- no guardar shared secret en campos visibles al usuario o en assets frontend;
- no asumir `/etc/odoo.conf`, `odoo.service`, `/var/log/odoo` ni paths de addons concretos en vistas/modelos.

## Tests obligatorios

- instalación/upgrade del addon en DB Odoo 18 DEV;
- health visible con service activo;
- estado de error claro con service detenido;
- comprobar que el browser no necesita conocer secreto/URL interna sensible;
- comprobar que el cliente HTTP usa configuración central y acepta un puerto local no-default;
- Settings/diagnóstico renderiza facts desconocidos sin inventar valores;
- suite Python existente, lint/type-check y tests Odoo aplicables.

## Acceptance criteria

- addon se instala/actualiza como módulo Odoo normal;
- desde Odoo un administrador puede comprobar si el service está healthy;
- detener el service produce un diagnóstico controlado, no un traceback crudo;
- browser no habla directamente con Assistant Service;
- endpoint/puerto y futuros deployment facts no están duplicados como constantes de frontend;
- la estructura de Settings permite añadir overrides de paths/providers posteriormente sin tocar application contracts;
- no se han adelantado features de M2;
- tests verdes.

## Antes de editar

1. Inspecciona la instalación Odoo real: addons_path, forma de arrancar tests y convenciones locales, tratándolas como hechos del DEV y no como defaults de producto.
2. Resume la UI/config mínima propuesta y qué valores son detected/configured/unknown.
3. Señala cualquier cambio necesario en el contrato HTTP antes de hacerlo.

## Después

1. Instala/actualiza el módulo en Odoo DEV.
2. Verifica estado con service activo y detenido.
3. Informa comandos y evidencia.
4. Lista cualquier path/nombre de deployment codificado y elimínalo o justifica por qué es una restricción de seguridad/perfil.
5. No avances a M1-09.

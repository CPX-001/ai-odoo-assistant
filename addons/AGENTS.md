# Reglas del addon Odoo

- Odoo 18 Community es el baseline.
- Mantener una UX Odoo-native.
- Durante el MVP, el browser habla con Odoo, no directamente con el Assistant Service.
- Derivar siempre la identidad efectiva server-side; no confiar en datos de identidad del browser.
- `ScreenContext` describe navegación, no concede autoridad.
- Releer registros mediante ORM bajo el usuario real antes de responder o actuar.
- No usar `sudo()` en caminos normales del agente.
- Respetar ACL, record rules, restricciones de campos y multi-company.

## Settings y deployment

- No hardcodear URL/puerto del Assistant Service ni paths de config/logs/addons del cliente en Python/XML/JS.
- Mostrar facts detectados/configurados/unknown de forma clara; no rellenar valores desconocidos con defaults del entorno DEV.
- Los overrides que un administrador pueda cambiar normalmente deben terminar en Settings/configuración persistida, no requerir editar código.
- Si un cambio requiere privilegios del host, Odoo no recibe root: usar setup boundary controlado o diagnóstico/fallback accionable.
- Mantener los detalles de filesystem/supervisor fuera del frontend; el addon consume contratos/status del Assistant Service.

Leer `docs/DEPLOYMENT_CONFIG.md` cuando una task añada Settings, Diagnostics, source o logs.

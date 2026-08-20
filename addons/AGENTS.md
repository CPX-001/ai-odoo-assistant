# Reglas del addon Odoo

- Odoo 18 Community es el baseline.
- Mantener una UX Odoo-native.
- Durante el MVP, el browser habla con Odoo, no directamente con el Assistant Service.
- Derivar siempre la identidad efectiva server-side; no confiar en datos de identidad del browser.
- `ScreenContext` describe navegación, no concede autoridad.
- Releer registros mediante ORM bajo el usuario real antes de responder o actuar.
- No usar `sudo()` en caminos normales del agente.
- Respetar ACL, record rules, restricciones de campos y multi-company.

No implementar el addon hasta que un task packet posterior lo autorice.

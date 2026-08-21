# Reglas del instalador

- Un único bootstrap privilegiado.
- Nunca dar root permanente al proceso Odoo.
- Instalación idempotente.
- El Assistant Service escucha sólo donde corresponda, preferentemente en loopback para el MVP.
- Crear DB y role propios del Assistant, separados de la DB Odoo.
- Automatizar antes que exigir configuración manual.
- Usar fallback manual sólo cuando el deployment impida automatizar.

## Adaptabilidad

- Los paths y nombres habituales son sólo hints de autodetección; nunca requisitos de cliente.
- Deben existir overrides sin modificar código para config Odoo, service/user, addons/source roots, data dir, logs y directorios/runtime del Assistant cuando apliquen.
- Un nombre de servicio explícito puede ser arbitrario; no exigir prefijo `odoo`.
- Odoo no tiene por qué estar gestionado por systemd aunque el Assistant Service sí lo esté en el perfil MVP.
- No exigir que `odoo.conf` exista ni que contenga todas las opciones; conservar valores desconocidos y resolverlos por runtime/configuración posterior cuando sea posible.
- No asumir PostgreSQL local o en el mismo cluster dentro de interfaces generales. El mismo cluster es el default recomendado del perfil self-hosted, no una constante de aplicación.
- Si la autodetección es ambigua, fallar de forma accionable o pedir override; nunca elegir silenciosamente.
- Mantener tests con layouts no convencionales para impedir regresiones hacia el entorno DEV.

Leer `docs/DEPLOYMENT_CONFIG.md` antes de introducir nuevos paths o assumptions de deployment.

# Reglas del instalador

## Flujo Git

- Trabajar siempre directamente sobre `main`; no crear ramas ni pull requests salvo orden explícita del usuario.

- Un único bootstrap privilegiado.
- Nunca dar root permanente al proceso Odoo.
- Instalación idempotente.
- El service escucha sólo donde corresponda, preferentemente en loopback para el MVP.
- Crear DB y role propios del Assistant, separados de la DB Odoo.
- Automatizar antes que exigir configuración manual.
- Usar fallback manual sólo cuando el deployment impida automatizar.

No implementar el instalador hasta que un task packet posterior lo autorice.

# Reglas del Assistant Service

## Flujo Git

- Trabajar siempre directamente sobre `main`; no crear ramas ni pull requests salvo orden explícita del usuario.

- Python 3.12+.
- Arquitectura basada en contracts, ports y adapters.
- `application` no depende de detalles de versión de Odoo.
- `contracts` no depende de FastAPI, Odoo, Codex ni storage.
- El `ReasoningEngine` no obtiene autoridad propia sobre Odoo.
- Usar PostgreSQL propio del Assistant.
- Nunca ejecutar SQL directo contra la DB productiva de Odoo.
- Exponer tools acotadas con resultados estructurados.
- Aplicar límites server-side; no confiar en límites expresados sólo en prompts.
- Evitar plugin frameworks prematuros.

## Configuración y deployment

- Leer `docs/DEPLOYMENT_CONFIG.md` para cualquier adapter/provider que toque filesystem, logs, source, servicios o PostgreSQL.
- No hardcodear paths, nombres de services, users, log files, addons roots o endpoints PostgreSQL del cliente dentro de `application`.
- Defaults locales pueden existir en adapters/entrypoints sólo como hints o valores sustituibles por configuración externa.
- Source/log providers deben recibir roots/units/paths resueltos; no descubrir el host mediante scans globales.
- Los valores desconocidos deben propagarse como capability/config pendiente, no rellenarse con el layout DEV.
- Cambiar un path/endpoint administrable no debe exigir modificar Python.

No implementar componentes fuera del task packet activo.

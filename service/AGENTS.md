# Reglas del Assistant Service

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

No implementar estos componentes hasta que un task packet posterior lo autorice.

# PROMPT CODEX — M0-05 JSON Schema y boundary tests

## Contexto

- Ejecutar después de M0-04 verde.
- Esta task endurece M0; no añade features.
- El criterio de aceptación de M0 exige JSON Schemas exportables y boundaries respetadas.

## Objetivo

Convertir los contratos y dependency rules de M0 en verificaciones ejecutables para detectar regresiones arquitectónicas desde el principio.

## Debes implementar

### JSON Schema

Crear una forma pequeña y determinista de exportar/generar JSON Schema para los contratos públicos de M0.

Debe cubrir al menos:

- `ScreenContext`
- `RecordRef`
- `Evidence`
- `ContextPack`
- `ToolSpec`
- `AnswerEnvelope`

Puede ser un script/module de desarrollo o tests que validen `model_json_schema()`. No crear un framework de schema registry.

Si se persisten snapshots de schema en `docs/contracts/`, justificarlo y mantenerlos generables; si no aportan valor todavía, bastan exports/tests reproducibles.

### Boundary tests

Añadir tests automáticos que fallen si se rompen las reglas principales de M0, especialmente:

- `odoo_ai.contracts` no importa FastAPI, Odoo, Codex, SQLAlchemy ni storage.
- `application` (si existe) no importa adapters/version clients.
- ports no importan adapters concretos.
- no aparecen clases estáticas por major como `SaleOrder18`, `SaleOrder19`, `AccountMove18`.

Usa la técnica más simple suficiente: inspección de imports/AST o una librería ligera sólo si aporta una mejora clara. No introduzcas una herramienta pesada de arquitectura.

## Fuera de scope

- Contract tests contra Odoo real.
- Integration/E2E.
- CI GitHub Actions.
- Version adapters.
- APIs HTTP.

## Tests obligatorios

```bash
pytest
ruff check .
mypy service/src
```

Además ejecuta la exportación/validación de JSON Schema elegida y demuestra que produce schemas serializables.

## Acceptance criteria

- Todos los contratos públicos M0 producen JSON Schema válido.
- Existe una prueba automática de las boundaries más importantes.
- Introducir deliberadamente un import prohibido sería detectado por los tests.
- La solución es pequeña y comprensible.
- No se añaden features de M1+.
- Suite completa verde.

## Antes de editar

Inspecciona la estructura real: adapta el test de boundaries a los packages que realmente existan, sin crear directories sólo para satisfacer el test.

## Después

Informa exactamente qué reglas quedan automatizadas y cuáles siguen siendo revisión humana. No continúes con M0-06 automáticamente.

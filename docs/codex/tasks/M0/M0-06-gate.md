# PROMPT CODEX — M0-06 Gate de milestone

## Contexto

- Ejecutar sólo después de M0-01..M0-05 completadas.
- Esta task no debe añadir features nuevas. Su función es inspeccionar, verificar y hacer únicamente correcciones pequeñas necesarias para cumplir M0.
- Usa como autoridad el Source of Truth, especialmente §§23, 24, 27, 29, 30 y 34.3.

## Objetivo

Demostrar de forma verificable que M0 está terminado y que el repo está preparado para iniciar M1 sin deuda arquitectónica básica.

## Inspección obligatoria

Revisa:

- layout real del monorepo;
- `service/pyproject.toml` y dependencias;
- package `odoo_ai`;
- contratos públicos;
- ports;
- tests de boundaries;
- configuración de pytest/ruff/mypy;
- `git diff`/estado del working tree;
- documentación M0 frente a implementación real.

## Verificaciones obligatorias

Ejecuta desde WSL los comandos reales equivalentes a:

```bash
pytest
ruff check .
mypy service/src
```

Verifica además:

1. Los contratos públicos M0 exportan JSON Schema.
2. `contracts` no importa Odoo, FastAPI, Codex, SQLAlchemy ni storage.
3. Los ports no dependen de adapters concretos.
4. No existen checks de major Odoo en `application`.
5. No existen clases de schema por versión (`SaleOrder18`, etc.).
6. No existe código funcional accidental de FastAPI, PostgreSQL, addon Odoo, scanner, retrieval, logs providers concretos o Codex App Server.
7. No se ha introducido `sudo()`, SQL directo a Odoo, shell libre o métodos genéricos del agente.

## Correcciones permitidas

Sólo fixes pequeños necesarios para hacer pasar los criterios anteriores:

- imports;
- typing;
- tests;
- nombres/exportaciones;
- configuración de tooling;
- documentación que haya quedado desfasada respecto al código real.

Si para cerrar M0 fuese necesaria una decisión arquitectónica nueva o un cambio grande, NO lo implementes silenciosamente: informa del bloqueo y propone ADR/task específica.

## Acceptance criteria — GATE M0

M0 está DONE únicamente si:

- monorepo/package layout coherente con el Source of Truth;
- contratos mínimos `ScreenContext`, `RecordRef`, `Evidence`, `ContextPack`, `ToolSpec`, `AnswerEnvelope` implementados;
- ports mínimos `ReasoningEngine`, `OdooGateway`, `LogProvider` implementados;
- JSON Schemas exportables;
- dependency boundaries automatizadas al nivel razonable para M0;
- `pytest`, lint y type-check verdes;
- ninguna feature de M1+ implementada prematuramente.

## Salida final

Entrega un informe breve con:

- resultado PASS/FAIL de M0;
- comandos ejecutados;
- tests totales/pasados;
- contratos y ports existentes;
- boundaries verificadas;
- deuda o riesgos pendientes;
- confirmación explícita de si se puede iniciar M1.

No empieces M1 automáticamente.

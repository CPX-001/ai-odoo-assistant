# M5-06 — Retrieval documental y tools de Knowledge

## Contexto

- Requiere M5-05 verde.
- El índice FTS vive en la Assistant DB y los documentos se tratan como datos no confiables.
- M4 ya aporta `ToolExecutor` y EvidenceLedger reutilizables.

## Objetivo

Añadir búsqueda lexical bounded y lectura de excerpts documentales vigentes, exponiéndolas como tools read-only que producen Evidence `DOCUMENT` checked sólo después de revalidar identidad/fingerprint de la versión actual.

## Debes implementar

### Retrieval application/storage

Una búsqueda FTS parametrizada y bounded con:

- query textual con cap;
- top-k con cap server-side;
- filtros allowlisted sólo si están soportados por metadata persistida (por ejemplo locale/provider);
- ranking reproducible suficiente para tests sin convertir scores exactos en contrato de producto;
- sólo documentos/chunks vigentes.

La búsqueda puede devolver candidatos ligeros, pero no debe convertir automáticamente cualquier match en Evidence checked.

### Refs documentales

Introduce refs opacos/lógicos suficientes para volver a localizar un chunk/documento sin aceptar physical path. Deben ligar como mínimo:

- documento/chunk;
- versión o fingerprint vigente;
- rango lógico/ordinal cuando corresponda.

### `knowledge.search`

- input Pydantic exacto;
- búsqueda FTS sólo sobre Assistant DB;
- resultados bounded con title/snippet lógico/ref/ranking sanitizado;
- no contenido completo ni physical path.

### `knowledge.read_excerpt`

- recibe únicamente refs emitidas/validables;
- vuelve a comprobar vigencia/fingerprint;
- devuelve excerpt bounded y provenance;
- versión stale/missing → error recuperable sin Evidence checked;
- versión vigente → Evidence `DOCUMENT`, status `CHECKED`, pointer lógico y fingerprint.

### Tool bindings

Registrar ambas tools explícitamente en `ToolExecutor` con riesgo `READ`/`METADATA`, límites por tool y schemas exactos. El texto del documento nunca cambia registry/policy.

## Fuera de scope

- embeddings;
- web search/fetch;
- edición de knowledge;
- HOW_TO orchestration;
- confiar en snippets como evidencia final sin `read_excerpt`.

## Tests obligatorios

- término conocido devuelve candidato esperado;
- top-k/caps efectivos;
- query con sintaxis SQL/adversarial se trata como texto/parámetro;
- documento retirado no aparece;
- ref/fingerprint stale falla sin Evidence checked;
- ref inventada/path-like falla cerrado;
- excerpt vigente produce Evidence DOCUMENT checked;
- bytes/lines/chars bounded;
- contenido con prompt injection no amplía tools;
- tool budgets y duplicados;
- suite, Ruff y mypy.

## Acceptance criteria

- existe un ciclo `search → ref → read_excerpt → Evidence checked`;
- el LLM no puede abrir documentos por path ni saltarse la comprobación de versión;
- retrieval usa PostgreSQL FTS y permanece provider-neutral por encima de storage;
- todavía no existe el workflow HOW_TO completo.

## Después

1. Documenta schemas finales de `knowledge.search` y `knowledge.read_excerpt`.
2. Muestra un ejemplo de stale ref y su fallo sanitizado.
3. No avances a M5-07.

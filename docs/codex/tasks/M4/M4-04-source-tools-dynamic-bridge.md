# M4-04 — Source tools y bridge de dynamic tools

## Contexto

- Requiere M4-03 verde.
- M3 ya implementa `FindSymbolRequest`, `FindModelExtensionsRequest`, `ReadExcerptRequest` y `SourceEvidenceService`.
- Codex App Server actual permite registrar dynamic tools en el lifecycle del thread; el detalle exacto debe tomarse de la versión probada en M4-01, no copiarse a application.

## Objetivo

Exponer a Codex únicamente las operaciones source necesarias para el vertical slice y completar el loop App Server → tool call → `ToolExecutor` → resultado → Codex, sin dar al modelo filesystem, shell ni paths libres.

## Debes reutilizar

- contracts y `SourceEvidenceService` de M3;
- `ToolSpec` existente;
- ToolExecutor/ledger M4-03;
- runtime source-root resolution ya probada en M3;
- client/lifecycle App Server M4-01/M4-02.

## Tool catalog M4

Ofrecer sólo equivalentes a:

1. `source.find_symbol`
   - input: `FindSymbolRequest`;
   - output bounded: candidatos lógicos, refs, líneas, module/model/name, fingerprint/provenance;
   - no path físico.

2. `source.find_model_extensions`
   - input: `FindModelExtensionsRequest`;
   - output bounded y conservador;
   - no afirmar runtime order si M3 no lo conoce.

3. `source.read_excerpt`
   - input: `ReadExcerptRequest` con `SourceRef` emitida por el índice;
   - revalida root + fingerprint;
   - devuelve líneas + `Evidence(kind=source)` checked;
   - stale → error/tool result explícito, nunca Evidence checked.

No expongas `source.rescan`, roots, glob, grep, read-file, directory listing ni Diagnostics admin como tools del modelo.

## Runtime wiring

Extrae/reutiliza el wiring M3 necesario para construir un source query service por turn sin duplicar la lógica de deployment:

- inventory/profile actual;
- roots resueltos/validados;
- Assistant DB session;
- cleanup de engine/session;
- trabajo síncrono de SQL/filesystem fuera del event loop cuando corresponda.

No hagas que `application` importe SQLAlchemy/path resolution.

## Dynamic tool bridge

Dentro del adapter Codex:

- convertir `ToolSpec` a la forma dynamic-tool exacta del protocolo probado;
- registrar las tools al iniciar el thread M4;
- correlacionar call id/request id/turn id;
- validar cada request antes de ejecutar;
- ejecutar sólo mediante `ToolExecutor`;
- serializar un resultado bounded;
- responder al App Server con la forma exacta esperada;
- unknown/duplicate/malformed call → fail closed;
- tool result no incluye exceptions, paths físicos ni secrets.

Si la API de Codex requiere activar una capability experimental, confínala al adapter y añade un probe/compatibility error claro. No filtres ese detalle a `application`.

## Fuera de scope

- Odoo generic tools adicionales: el current record se preleerá determinísticamente en M4-05;
- logs como agent tool;
- QUERY/HOW_TO/RAG;
- writes/actions;
- cambiar el scanner M3.

## Tests obligatorios

- ToolSpecs generados desde schemas reales;
- fake Codex pide `find_model_extensions` → `find_symbol` → `read_excerpt` y completa;
- tool inventada → rechazo;
- input con path libre/extra field → rechazo;
- SourceRef manipulada/stale → no Evidence checked;
- cap de resultados/excerpt se conserva;
- physical root nunca sale en tool result;
- duplicate tool request no amplía effects/budgets;
- compatibilidad/probe cuando dynamic tools no estén soportadas;
- suite, Ruff y mypy.

## Acceptance criteria

- Codex puede obtener source exacto sólo a través de tools M3 allowlisted;
- todas las ejecuciones pasan por ToolExecutor;
- un source excerpt válido entra en el evidence ledger;
- no hay acceso genérico al filesystem;
- el engine puede completar un turn fake con al menos un tool roundtrip.

## Después

1. Documenta los nombres/schemas finales de las 3 tools.
2. Muestra un roundtrip fake y uno real si el App Server/model disponible solicita tools de forma reproducible.
3. No avances a M4-05.

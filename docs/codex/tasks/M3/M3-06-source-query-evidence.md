# M3-06 — Búsqueda de símbolos y lectura de excerpts

## Contexto

- Requiere scanner completo M3-05.
- M4 necesitará pedir evidencia bajo demanda, pero M3 no implementa ReasoningEngine ni ToolCatalog genérico.
- El Source of Truth exige operaciones equivalentes a `source.find_symbol`, `source.find_model_extensions` y `source.read_excerpt`.

## Objetivo

Exponer servicios internos estructurados y acotados para localizar source indexado y leer fragments exactos, sin aceptar paths arbitrarios.

## Contratos que NO puedes romper

- `read_excerpt` sólo puede leer ficheros previamente indexados bajo roots permitidos;
- no hay filesystem browser genérico;
- no hay tool registry/plugin framework;
- evidence source se marca como técnica y checked/inferred según corresponda.

## Debes reutilizar

- contracts `Evidence`;
- repositorios M3-02;
- índice estructural M3-04/M3-05;
- patrón de endpoints admin/machine-auth existente cuando Diagnostics necesite consumir estas operaciones.

## Debes implementar

### 1. `find_symbol`

Input bounded:
- model opcional;
- symbol/method/XML id;
- module opcional;
- max results.

Prioridad:
1. match exacto estructural;
2. match normalizado;
3. fuzzy/trigram sólo si encaja limpiamente en la Assistant DB sin introducir infraestructura innecesaria.

No hacer vector search.

Salida:
- candidatos con source ref estable;
- module/kind/model/name/path/líneas/fingerprint/provenance;
- score/motivo de match si aplica.

### 2. `find_model_extensions`

Dado un modelo como `sale.order`:
- encontrar `_name/_inherit` indexados relacionados;
- agrupar por módulo/fichero;
- no afirmar orden runtime exacto si no está comprobado.

### 3. `read_excerpt`

Aceptar únicamente un `SourceRef`/id emitido por el índice:
- resolver path server-side;
- revalidar root;
- verificar fingerprint actual;
- leer sólo rango solicitado alrededor del símbolo;
- cap de líneas y bytes;
- incluir números de línea;
- si hash cambió desde el scan → `stale_source`, no entregar como checked.

Nunca aceptar un path libre desde request.

### 4. Evidence

Convertir resultados relevantes a `Evidence(kind=source)` con:
- `status=checked` si fingerprint vigente;
- pointer;
- observed_at/scan info;
- sensitivity=technical;
- fingerprint.

No meter el repo completo en payload.

## Fuera de scope

- Codex/dynamicTools;
- docs RAG;
- embeddings;
- arbitrary grep del filesystem;
- logs.

## Restricciones

- max results;
- max excerpt lines;
- max bytes;
- path interno nunca se toma como autoridad desde cliente;
- no leer fichero stale como evidencia checked.

## Tests obligatorios

- `sale.order/action_confirm` exact match;
- XML id match;
- model extensions;
- unknown symbol;
- max results;
- source ref manipulado;
- symlink/path escape;
- changed hash before excerpt → stale;
- excerpt devuelve líneas correctas;
- payload bounded.

## Acceptance criteria

- `action_confirm` puede localizarse y leerse con líneas exactas;
- un path arbitrario no es una entrada válida;
- source stale se detecta;
- output es consumible por M4 sin cambiar storage/scanner.

## Antes de editar

1. Define input/output schemas finales.
2. Explica estrategia exact/normalized/trigram.
3. Define caps.

## Después

1. Muestra find + excerpt del fixture.
2. Demuestra rechazo de path libre/stale hash.
3. Ejecuta tests.
4. No avances a M3-07.

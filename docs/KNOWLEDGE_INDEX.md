# Knowledge index y PostgreSQL FTS

M5-05 introduce una ingesta documental incremental dentro de la base PostgreSQL
propia del Assistant. No accede a la base Odoo, no hace fetching web y no usa
embeddings ni extensiones vectoriales.

## Provider inicial

`FilesystemKnowledgeProvider` acepta una raíz absoluta por provider. Las fuentes
se configuran explícitamente mediante `ODOO_AI_KNOWLEDGE_SOURCES`, por ejemplo:

```json
[
  {
    "provider_id": "customer.manuals",
    "root": "/srv/customer/assistant-knowledge",
    "locale": "es-ES"
  }
]
```

No existe una raíz por defecto. La configuración rechaza paths relativos o con
`..`, IDs duplicados y locales inválidos. El provider sólo admite UTF-8
`text/plain` (`.txt`) y `text/markdown` (`.md`, `.markdown`). Ignora otros
formatos, rechaza binarios y symlinks, comprueba el destino real del descriptor
abierto y aplica límites de documentos, bytes por fichero, bytes totales,
profundidad y tiempo. Los contratos y diagnósticos sólo incluyen
`provider_id`/`document_id` lógicos; nunca incluyen la raíz física.

## Persistencia

La revisión Alembic `0006_m5_05_knowledge_fts` añade:

- `knowledge_document`: identidad única por instancia, provider y documento
  lógico; título, locale, media type, fingerprint, tamaño, timestamps y estado
  `current`/`retired`.
- `knowledge_chunk`: identidad determinista por versión y ordinal, fingerprint
  de documento/chunk, texto, offsets, líneas, tamaños, configuración FTS y
  `search_vector` PostgreSQL.

Índices principales:

- `ix_knowledge_document_instance_provider_status` para seleccionar únicamente
  versiones vigentes dentro del provider/instancia;
- `ix_knowledge_document_fingerprint` para comprobaciones de versión;
- `ix_knowledge_chunk_document` para reconstrucción ordenada;
- `ix_knowledge_chunk_search_vector`, GIN sobre `tsvector`, para búsqueda FTS.

La configuración FTS se pasa al store (`simple` por defecto) y queda persistida
por chunk. No se infiere del idioma del cliente ni se fija a español. Un
fingerprint sin cambios conserva las filas/chunk IDs existentes; un cambio
reemplaza los chunks dentro de la misma transacción del caller; un documento no
visto tras un scan completo pasa a `retired`. Un scan parcial nunca retira
documentos que no alcanzó a observar.

## Chunking

El texto se normaliza a saltos `\n` y se divide de forma determinista con límites
independientes de caracteres y bytes UTF-8. El algoritmo prefiere cerrar el
chunk en un salto de línea, conserva ordinal, offsets de carácter y rango de
líneas, y genera un fingerprint ligado a la versión del documento. Los defaults
son 2.000 caracteres, 8.000 bytes y 4.096 chunks máximos por documento; todos
son sustituibles dentro de los caps del contrato.

## Diagnóstico sanitizado

Un scan fixture de un documento Markdown produce una forma equivalente a:

```json
{
  "metrics": {
    "documents_seen": 1,
    "documents_indexed": 1,
    "documents_unchanged": 0,
    "documents_retired": 0,
    "errors": 0,
    "chunks": 1,
    "duration_ms": 1
  },
  "issue_codes": [],
  "complete": true
}
```

La duración es observada y variable. La respuesta no contiene roots, paths
físicos ni contenido documental completo.

## Retrieval y tools

M5-06 añade exactamente dos tools read-only:

| Tool | Input | Resultado |
|---|---|---|
| `knowledge.search` | `KnowledgeSearchRequest` | candidatos FTS ligeros, sin Evidence |
| `knowledge.read_excerpt` | `KnowledgeReadExcerptRequest` | excerpt acotado + Evidence `document/checked` |

`knowledge.search` acepta `query` de hasta 256 caracteres, `top_k` entre 1 y
20, y filtros opcionales exactos por `provider_id` y `locale`. La consulta usa
`plainto_tsquery` parametrizado con la configuración FTS persistida de cada
chunk. Sólo une documentos `current` cuyo fingerprint coincide con el chunk.
Los candidatos exponen posición, título, provider/document ID lógico, locale,
media type, snippet de hasta 360 caracteres y un `KnowledgeRef`; no producen
Evidence comprobada.

La ref liga:

```json
{
  "document_uuid": "11111111-1111-4111-8111-111111111111",
  "chunk_uuid": "22222222-2222-4222-8222-222222222222",
  "provider_id": "customer.manuals",
  "document_id": "payments/terms.md",
  "document_fingerprint": "sha256:<64 hex>",
  "chunk_fingerprint": "sha256:<64 hex>",
  "ordinal": 0
}
```

`knowledge.read_excerpt` sólo acepta esa ref y caps de 1-80 líneas, 128-8.000
caracteres y 256-16.000 bytes. Antes de responder vuelve a comparar instancia,
estado vigente, UUIDs, IDs lógicos, ordinal y ambos fingerprints. La Evidence
resultante usa un pointer lógico, marca el contenido como
`untrusted_document` y no incluye paths físicos.

Una ref cuya versión cambió, fue retirada, falta o fue inventada falla de forma
recuperable y no entra en el `EvidenceLedger`:

```json
{
  "ok": false,
  "error": {"code": "knowledge_ref_stale"}
}
```

El registry se construye explícitamente por turn y aplica los budgets agregados
de `ToolExecutor`; el texto indexado no puede registrar tools ni cambiar policy.

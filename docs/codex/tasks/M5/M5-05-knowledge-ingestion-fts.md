# M5-05 — Knowledge ingestion y PostgreSQL FTS

## Contexto

- Requiere M5-04 verde.
- `docs/ARCHITECTURE.md` fija PostgreSQL FTS como primera estrategia documental.
- La Assistant DB es propia y sí puede almacenar índices/knowledge; la DB Odoo sigue aislada.

## Objetivo

Crear una ingesta documental incremental, reproducible y bounded en la Assistant DB, con fingerprints y chunks aptos para PostgreSQL FTS, sin introducir embeddings/vector DB.

## Antes de decidir implementación

Inspecciona migrations/storage existentes y la política de deployment. Define el conjunto mínimo de formatos/proveedores que aporte un E2E útil. Prefiere texto/Markdown y, si ya existe una forma segura y simple de extraerlo, HTML; no añadas parsers pesados sin necesidad.

## Debes implementar

### Contratos/provider boundary

Una boundary pequeña para documentos configurados que produzca datos equivalentes a:

- source/provider id lógico;
- document id lógico;
- title;
- locale opcional;
- media/type soportado;
- contenido textual bounded;
- fingerprint;
- observed/modified metadata segura.

El provider inicial recibe roots/sources explícitamente configurados y validados. No recibe paths libres desde el modelo.

### Seguridad filesystem

Si el provider inicial usa filesystem:

- roots resueltos por configuración/override;
- bloquear escapes por `..`/symlink;
- no recorrer fuera de roots;
- caps por fichero, total de scan y número de docs;
- ignorar binarios/formatos no soportados de forma explícita;
- logical paths en persistencia/evidence; no physical paths browser-facing.

### Persistencia

Añade migraciones/modelos mínimos, por ejemplo:

- `knowledge_document`;
- `knowledge_chunk`;
- scan/run metadata sólo si aporta idempotencia/diagnóstico.

Cada documento/chunk debe tener identidad estable, fingerprint/version y estado suficiente para distinguir vigente/retirado.

### Chunking + FTS

- chunking determinista con caps de caracteres/bytes;
- conservar orden y offsets/líneas cuando el formato lo permita;
- indexar texto con PostgreSQL FTS;
- lenguaje/config FTS explícita y sustituible; no asumir idioma del cliente como constante;
- índices necesarios para búsqueda;
- unchanged fingerprint → no reescritura innecesaria;
- changed → reemplazo transaccional;
- missing/removed → dejar de ser recuperable como vigente.

No almacenar embeddings ni añadir dependencia de vector extension en M5.

### Diagnóstico

Exponer métricas sanitizadas: docs vistos/indexados/unchanged/retired/errors, chunks y duración; sin physical paths ni contenido completo.

## Fuera de scope

- retrieval/tool calls;
- web crawling/fetching;
- OCR;
- embeddings/vector DB;
- sync universal con múltiples SaaS;
- UI final HOW_TO.

## Tests obligatorios

- fresh migration y upgrade desde M4;
- ingest inicial + idempotencia;
- modificación cambia fingerprint/chunks;
- borrado/retirada deja de ser vigente;
- symlink/path escape rechazado;
- caps de doc/chunk/scan;
- unicode/acentos y locale;
- FTS encuentra término conocido;
- no physical path en contratos/traces públicos;
- layout/root no-default configurable;
- suite, Ruff y mypy.

## Acceptance criteria

- la Assistant DB contiene knowledge documental versionado y buscable por FTS;
- la ingesta es incremental y reproducible;
- no existe vector search ni fetching web;
- un documento stale puede distinguirse de su versión vigente.

## Después

1. Documenta tablas/índices y estrategia de chunking final.
2. Muestra métricas de un scan fixture sin paths sensibles.
3. No avances a M5-06.

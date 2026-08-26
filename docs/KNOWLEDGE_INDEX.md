# Knowledge and retrieval status

This document supersedes the former sidecar PostgreSQL FTS Knowledge Index specification.

## Current state

At the audited embedded-runtime baseline, the core capability provider package contains `odoo_query`, `odoo_actions`, `odoo_batch` and `odoo_runtime`. It does **not** currently contain the old `knowledge.search`, `knowledge.read_excerpt` or a general document/vector RAG provider.

The earlier Knowledge Index implementation under the retired Assistant Service is historical evidence only. Its SQLAlchemy/Alembic tables, separate Assistant PostgreSQL database, service-side FTS APIs and sidecar ingestion lifecycle are not current deployment/runtime contracts.

## What remains useful from the old design

Several principles remain valid independent of storage technology:

- retrieval results need stable provenance;
- ingestion/indexing state should be observable;
- excerpts and outputs must be bounded;
- user-provided/retrieved text is data, never policy;
- exact/lexical retrieval and semantic retrieval solve different problems;
- source code/XML/runtime facts often need structured indexes rather than generic embeddings;
- retrieval must respect the same installation/user context as the rest of the assistant.

These are design constraints, not evidence that the old sidecar index should be restored.

## Target retrieval architecture

A future embedded retrieval layer should compose evidence providers behind host-owned contracts, for example:

```text
Retrieval planner/provider layer
  |
  +--> live runtime/schema/configuration
  +--> Odoo business data
  +--> source/XML structural index
  +--> logs/diagnostics
  +--> internal documents/Knowledge/attachments
  +--> lexical/FTS search
  +--> semantic/vector search where it improves recall
```

Results should normalize provenance, trust level, freshness/fingerprint and bounded excerpts so reasoning can compare evidence without treating any retrieved instruction as authority.

## Storage choice is not predetermined

The current project does not require pgvector, Chroma, Qdrant, Neo4j, LlamaIndex or a separate retrieval service. Choose a store only after the desired corpus/query/eval demonstrates a need. Odoo/PostgreSQL-native solutions are preferred when they satisfy the requirement without a new operational component.

## Source intelligence

For questions about a concrete installation, source/XML/runtime evidence can be more valuable than general document embeddings. Future work should preserve installation-local module/version evidence and support deterministic Odoo validations (for example model/field/view/domain relationships) where feasible.

## Lifecycle direction

For persistent or temporary knowledge sources, a reasonable product lifecycle is:

```text
discovered/uploaded -> processing -> indexed -> active
                                  \-> error
```

Reprocessing, deletion, ACL changes and source freshness must invalidate/refresh derived evidence explicitly.

## Security

- Never let a retrieved document modify host policy.
- Do not index secrets merely because they are readable on disk.
- Apply ACL/provenance before returning business/internal content to the model.
- Do not dump large files or binary/base64 payloads into prompts.
- Keep record, byte, chunk and latency budgets host-owned.

## Reintroducing knowledge

When implementing general knowledge/RAG, create current embedded capabilities/providers and tests/evals. Do not reconnect the old sidecar Knowledge API merely because historical code already exists.
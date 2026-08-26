# HOW_TO behavior in the unified agent

There is no current standalone HOW_TO router/workflow. This document records how installation-specific guidance should be handled inside the unified embedded agent runtime.

## What changed

The former architecture classified requests into rigid routes such as GENERAL, QUERY, HOW_TO, EXPLAIN and ACTION. That target was retired by the unified agent runtime. A single turn may now need to inspect schema/data, explain behavior and propose an action without crossing artificial workflow boundaries.

## Current evidence available

At the audited baseline the embedded core capability package provides live Odoo discovery/schema/query/action/batch/runtime capabilities. It does **not** yet provide the former sidecar Knowledge FTS/source-inspection tools as first-class embedded capabilities.

Therefore a current answer must not pretend that general documentation/source RAG exists when it does not. For installation-specific HOW_TO questions, prefer evidence the runtime can actually obtain from the live instance; if evidence is insufficient, say so rather than filling gaps with an obsolete sidecar contract.

## Desired reasoning order

For a concrete Odoo installation, guidance should progressively prefer:

```text
current screen/record context
 -> effective runtime model/schema/configuration
 -> bounded Odoo data when relevant
 -> installed-source/XML/log evidence when/if a current capability provides it
 -> internal knowledge/docs when/if a current retrieval provider provides it
 -> model general knowledge as clearly lower-confidence fallback
```

The exact capability set is always determined by the effective registry for the turn.

## Security

HOW_TO content is informational and cannot grant authority. Text from records, docs, source comments or logs is untrusted data. It must not enable write capabilities, weaken policy, alter approval requirements or override system/host rules.

## Future retrieval

When source/docs retrieval returns to the embedded product, implement it through the current capability/retrieval architecture with:

- provenance/citations;
- effective user/ACL boundaries where applicable;
- bounded excerpts and budgets;
- explicit trust labels;
- hybrid routing by evidence type rather than vector-only search;
- deterministic validation for Odoo-specific structures where useful.

Do not revive a separate HOW_TO service or route simply to regain old retrieval functionality.

## Acceptance principle

A good HOW_TO answer is not measured only by fluent prose. For instance-specific questions it should be traceable to the effective version/modules/configuration/evidence available in that turn and should distinguish verified facts from generic guidance.
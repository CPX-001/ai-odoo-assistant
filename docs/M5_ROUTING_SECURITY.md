# M5 routing and panel security

M5 introduced separate read-only workflow boundaries. The product UI now places an
automatic chat facade in front of those boundaries: the user does **not** choose
`EXPLAIN`, `QUERY`, `HOW_TO` or `ACTION` manually.

## Automatic product routing

The browser sends only the message, the untrusted `ScreenContext` hint and an optional
conversation id to `/odoo_ai/v1/chat`. Odoo derives the effective user server-side and
chooses the narrow internal boundary before granting any authority:

```text
single chat
    ├─ contextual explanation -> EXPLAIN boundary
    ├─ live ORM question       -> QUERY boundary
    ├─ navigation/how-to       -> HOW_TO boundary
    ├─ requested write         -> ACTION preview boundary
    └─ code/docs/general       -> GENERAL read-only boundary
```

The routing decision is internal product behavior, not browser authority. Existing
legacy endpoints remain for compatibility, but the standard panel uses only the chat
facade and action-decision endpoint.

`ScreenContext` remains a navigation hint. QUERY may resolve a different visible/readable
model from Odoo navigation metadata instead of being mechanically tied to the model that
happens to be open. ACTION remains intentionally stricter: the current implementation
only grants preview authority for a concrete current record/model; it never silently
turns a cross-model request into a write on the open record.

## Least-privilege boundaries

The facade does not merge write authority or expose generic execution. Internally the
existing registries remain bounded:

| Boundary | Dynamic tools visible to Codex |
| --- | --- |
| EXPLAIN | `source.find_symbol`, `source.find_model_extensions`, `source.read_excerpt` |
| QUERY | `odoo.get_effective_schema`, `odoo.query_records`, `odoo.aggregate_records` |
| HOW_TO | `knowledge.search`, `knowledge.read_excerpt` |
| ACTION | allowlisted schema/preview tools only; approval and commit stay host-side |
| GENERAL | source tools plus pre-retrieved persistent knowledge; no Odoo write authority |

GENERAL exists so code/backend/documentation questions do not require an artificial
saved-record context. Persistent knowledge is retrieved from Assistant PostgreSQL before
the reasoning turn; source tools use the persistent source index and revalidate excerpts.
No boundary exposes shell, arbitrary SQL, Python execution, `sudo()`, generic
`execute_method` or generic `execute_kw`.

## Conversation state

User-visible conversation history lives in the Assistant PostgreSQL database and is
isolated by Odoo database + effective uid. The memory supplied to reasoning is bounded;
Codex threads remain ephemeral and are not the product memory store.

Unsent composer text is a browser draft only. It is saved per host/user/conversation so
closing the panel or refreshing Odoo does not discard it. It grants no authority and is
sent to the server only when the user submits it.

## Browser response

Odoo returns only sanitized chat presentation data: answer, confidence, bounded
limitations/citations, conversation id and (for ACTION) the validated preview. Delegation
and machine secrets, effective authority claims, internal URLs, physical roots/paths,
raw tool transcripts and raw query rows do not cross to the browser.

The Owl template renders all user/model/source/document text with escaped text directives;
it contains no `t-raw`, `innerHTML`, dynamic arbitrary links or HTML/Markdown renderer.

## Source and knowledge lifecycle

Source and knowledge are installation-level persistent indexes, not per-model or
per-reasoning-model state. Install/upgrade hooks ask the local Assistant Service to build
or refresh them. Manual maintenance operations remain available for diagnostics and
reindexing.

An isolated unreadable or unparsable source file no longer makes the whole useful source
index unavailable. Valid files are persisted and the scan reports `partial_scan`; stale
rows are only deleted after a complete traversal. Global safety limits/timeouts still
fail the scan.

## Security invariants retained

- effective identity/company context is derived in Odoo server-side;
- live business records are read through Odoo ORM under ACL/record rules;
- writes remain proposal -> preview -> explicit approval -> commit -> verification;
- no model output can manufacture approval or write authority;
- source/document contents remain untrusted data;
- request, response, tool and evidence budgets stay server-enforced.

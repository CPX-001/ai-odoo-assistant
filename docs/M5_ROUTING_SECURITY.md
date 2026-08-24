# M5 routing and panel security

> Documento histórico del gate M5. El router por categorías fue sustituido por
> `AgentTurnService` mediante ADR-014; no describe el routing activo.

M5 introduced separate read-only workflow boundaries. The product UI now places an
automatic chat facade in front of those boundaries: the user does **not** choose
`EXPLAIN`, `QUERY`, `HOW_TO` or `ACTION` manually.

## Automatic product routing

The browser sends only the message, the untrusted `ScreenContext` hint and an optional
conversation id to `/odoo_ai/v1/chat`. Odoo derives the effective user server-side and
builds a bounded candidate list from models that are actually visible and readable under
that actor. A tool-free Codex structured-output turn interprets the original message,
effective locale, recent bounded history, current screen and those candidates:

```text
single chat
    ├─ contextual explanation -> EXPLAIN boundary
    ├─ live ORM question       -> QUERY boundary
    ├─ navigation/how-to       -> HOW_TO boundary
    ├─ requested write         -> ACTION preview boundary
    └─ code/docs/general       -> GENERAL read-only boundary
```

The router is semantic and multilingual; it does not maintain language-specific keyword
or model-alias dictionaries. Its output is restricted to `workflow + target_model` plus a
self-contained same-language reformulation that may only resolve references supported by
bounded recent history. It has no tools or execution authority and must select a target
from the Odoo-provided list. Odoo persists the original user text, not the reformulation.
Odoo validates both values again before signing a workflow delegation. Responses follow
the request language, falling back to the effective Odoo locale when it is ambiguous.

The routing decision is internal product behavior, not browser authority. Existing legacy
endpoints remain for compatibility, but the standard panel uses only the chat facade and
action-decision endpoint.

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

ACTION exposes all registered preview-only families instead of selecting them with
prompt-language regular expressions. Codex chooses the semantic family, while the host
still enforces the three-call global budget, per-tool caps, effective write schema,
current-record target and proposal reconciliation. A patch of the current record cannot
fall back to record creation after malformed arguments. Free-form chat text never grants
approval; only the explicit Odoo action-decision route can start commit and verification.

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

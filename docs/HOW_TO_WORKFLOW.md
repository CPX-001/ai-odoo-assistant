# HOW_TO read-only workflow

M5-07 adds a dedicated `HOW_TO` turn for installation-aware guidance. The browser calls only Odoo (`/odoo_ai/v1/how-to`); Odoo derives the effective user, companies and database, signs a short-lived delegation, and calls the Assistant Service (`/v1/turns/how-to`). The browser never receives the delegation token, shared secret, internal endpoint, physical knowledge path, raw action payload or raw Evidence.

## Authority and registry

The HOW_TO delegation contains only:

- `navigation`, always;
- `fields_get`, only when the current screen identifies a valid runtime model;
- no record ids, record reads, QUERY authority, write authority or action authority.

The Assistant preloads visible navigation and the effective runtime schema through that delegation. Codex receives exactly `knowledge.search` and `knowledge.read_excerpt` as dynamic tools. Labels, schema metadata, document text, snippets and the user message remain untrusted data; none can add a tool or change policy.

## Evidence and confidence rules

All returned citations resolve to `CHECKED` Evidence produced in the same turn:

- `navigation`: logical visible menu id/path, target model and allowlisted view modes;
- `schema`: model, schema fingerprint and the bounded visible field name/label/type set;
- `document`: logical provider/document id, chunk ordinal, line range and current document fingerprint.

Physical paths and raw Odoo action values are not part of the response contract.

The host applies these postconditions:

1. `workflow` must be `HOW_TO` and `proposed_action` must be null.
2. Unknown, conflicting, unchecked or malformed evidence references fail closed.
3. If no relevant visible menu exists, model-authored route text is replaced with a low-confidence installation limitation.
4. A backtick-delimited installation field containing an underscore is checked against the effective schema. An absent field causes the assertion to be removed and replaced by a low-confidence limitation.
5. A document citation without a navigation citation explicitly says that documentation alone does not confirm a route in this installation.
6. `HIGH` requires checked navigation and documentation citations; when an effective schema was available, it also requires a schema citation. Missing support degrades confidence to `MEDIUM` or `LOW`.
7. Answers, limitations, citations, navigation nodes, schema fields, tool calls, evidence count and request/response bytes are bounded.

General model knowledge can only appear as a degraded answer with an explicit limitation; it is never represented as a checked installation fact.

## Fixture

For a user on `sale.order`, a verified response can cite:

```text
answer: Ve a Sales > Orders y usa el campo `state` para comprobar el estado.
confidence: high
citations:
  navigation: menu 11, Sales > Orders, target sale.order, list/form
  schema: sale.order, sha256:<runtime schema>, fields [name, state]
  document: odoo-docs/sales/orders.md, chunk 0, lines 10-12,
            sha256:<current document version>
```

If `Sales > Orders` is not visible for that user, the service does not return that route as an installation fact, even when a document or prompt contains it.

## Scope boundary

HOW_TO remains read-only. It does not execute steps, query business records, fetch the web, persist conversation state, preview writes, request approvals or perform actions. Multi-workflow panel routing and hardening beyond this dedicated path belong to M5-08.

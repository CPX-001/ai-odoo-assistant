# M5 routing and panel security

M5-08 integrates the three read-only workflows in one Odoo-native panel without
combining their authority.

## Workflow selection

The user explicitly selects `EXPLAIN`, `QUERY` or `HOW_TO` in the panel. The
browser sends that value only as an untrusted routing hint to
`/odoo_ai/v1/turn`. Odoo validates it against the fixed read-only allowlist
before preparing any delegation or contacting the Assistant Service:

```text
EXPLAIN -> v1 record delegation -> /v1/turns/explain
QUERY   -> q1 model/query delegation -> /v1/turns/query
HOW_TO  -> v1 navigation/schema delegation -> /v1/turns/how-to
```

`ACTION`, unknown values and values recovered from records, menu labels,
metadata, documents or model output are rejected. A workflow cannot be changed
by a tool call or by Evidence because routing finishes before the registry is
built.

The dedicated legacy browser routes remain available for M4/M5 compatibility,
but the integrated panel uses only `/odoo_ai/v1/turn`.

## Least-privilege registries

The Assistant Service keeps separate endpoints and constructs exactly one
registry per turn:

| Workflow | Dynamic tools visible to Codex |
| --- | --- |
| EXPLAIN | `source.find_symbol`, `source.find_model_extensions`, `source.read_excerpt` |
| QUERY | `odoo.get_effective_schema`, `odoo.query_records`, `odoo.aggregate_records` |
| HOW_TO | `knowledge.search`, `knowledge.read_excerpt` |

HOW_TO navigation and effective schema are deterministic pre-context, not
general tools. No registry contains write, preview, approval, business action,
shell, SQL, Python, filesystem or generic method execution.

## Browser response

Odoo returns only:

- the selected workflow and turn id;
- answer text, confidence and bounded limitations;
- sanitized logical citations for the selected workflow.

The response excludes delegation and machine secrets, user/company authority,
internal URLs, physical roots/paths, raw query rows, raw Evidence and tool
transcripts. A response whose `workflow` differs from the selected workflow, or
which contains a citation kind from another workflow, fails closed.

The Owl template renders answer, limitations and every citation field with
escaped text directives. It contains no `t-raw`, `innerHTML`, dynamic links or
HTML/Markdown renderer. Record values, menu labels, field labels and document
titles therefore remain untrusted text.

## Diagnostics

`/v1/admin/status` exposes sanitized `workflow_capabilities` for `query`,
`navigation`, `knowledge` and `how_to`. These states describe whether their
runtime dependencies are present and note that user-specific validation occurs
per turn.

They do not change global readiness. `FULLY_READY` continues to require the
Assistant DB/migrations, Codex, source, logs and a valid scan as established by
the Source of Truth and earlier milestones.

## Hardening evidence

The M5-08 test set covers:

- explicit routing and rejection before authority creation;
- cross-workflow response/citation confusion;
- exact disjoint registries and absence of M6 tools;
- ACL denial before HOW_TO reasoning;
- manipulated QUERY schemas/arguments and stale knowledge references;
- unknown/duplicate tool calls, event floods, timeouts, interruption and
  runtime cleanup inherited from the M4 ToolExecutor/App Server hardening;
- prompt injection and canary redaction in records, metadata, source and
  documents;
- HTML/JavaScript payloads rendered as text;
- request/response/tool/evidence budgets;
- browser network restricted to authenticated Odoo RPC.

M5 remains read-only.

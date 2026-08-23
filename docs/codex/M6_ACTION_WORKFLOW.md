# M6 ACTION workflow

## Boundary and registry

ACTION is selected before a turn is prepared. Odoo derives the authenticated
user, active company set, database and current record, then signs a short-lived
`p1` authority limited to the visible write schema and one effect-free preview.
The ACTION registry contains exactly:

- `odoo.get_effective_write_schema` (`METADATA`);
- `odoo.preview_record_patch` (`WRITE_PREVIEW`).

The default registry remains read/metadata-only. The reasoning engine never
receives approval, commit, arbitrary method, shell, SQL or Python tools. A
preview created by the host is validated against the current turn, target,
fingerprints and checked preview evidence before its opaque proposal handle is
returned.

## Approval and execution

Chromium sends only `proposal_id` and `decision` to Odoo's authenticated
`/odoo_ai/v1/action-decision` JSON-RPC route. Odoo ignores browser identity and
derives database, uid, company and allowed companies from `request.env`. The
Assistant resolves the stored proposal, persists the terminal decision, and on
approval executes the immutable stored payload through the existing M6
one-shot commit and reread verification services. This operation has no
reasoning-engine dependency.

The browser never receives the `p1` token, action authority, shared secret,
payload/precondition fingerprints, authoritative values or raw backend errors.
Browser traffic remains Chromium → Odoo; only Odoo communicates with the local
Assistant Service.

## Panel states

| State | User-facing meaning | Further action |
|---|---|---|
| preview pending | Exact target, fields, before/after, warnings and expiry are visible | Approve or cancel once |
| executing/verifying | Odoo is committing and rereading; controls are disabled | Wait |
| verified | Reread exactly matched the approved values | Success |
| rejected | Decision is terminal and no write occurred | Create a new preview if desired |
| stale | Current values no longer match the preview | Generate a new preview; no force option |
| failed | Commit failed deterministically | Review and generate a new preview if appropriate |
| execution unknown | Commit outcome cannot be established | No automatic retry |
| committed unverified | Commit was acknowledged but reread did not prove the result | Not presented as success |

All model output, field labels, values and warnings are rendered with Owl
escaping (`t-esc`); ACTION templates contain no `t-raw` or `innerHTML` sink.
Diagnostics expose only a minimal `workflow_capabilities.action` state derived
from Assistant DB/migrations, instance discovery and reasoning readiness.

## Verification evidence

Deterministic tests cover registry isolation, same-turn proposal binding,
cross-user/database/company rejection, terminal cancel, replay, stale, expiry,
tampering, XSS data and ambiguous-result reread. The disposable real runner is
documented in `tests/e2e/README.md` and emits sanitized correlation/tool/write
evidence for the M6 gate report.

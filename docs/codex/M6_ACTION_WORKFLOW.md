# M6 ACTION workflow

## Boundary and registry

ACTION is selected before a turn is prepared. Odoo derives the authenticated
user, active company set, database and current record, then signs a short-lived
`p1` authority limited to the visible write schema and one effect-free preview.
The supported ACTION preview registry is closed to:

- `odoo.get_effective_write_schema` (`METADATA`);
- `odoo.preview_record_patch` (`WRITE_PREVIEW`);
- `odoo.preview_record_create` (`WRITE_PREVIEW`).
- `odoo.preview_business_action` (`WRITE_PREVIEW`).

For each turn the host narrows that set deterministically to the relevant
family plus schema when needed; this reduces tool ambiguity without granting a
new capability.

The default registry remains read/metadata-only. The reasoning engine never
receives approval, commit, arbitrary method, shell, SQL or Python tools. A
preview created by the host is validated against the current turn, target,
fingerprints and checked preview evidence before its opaque proposal handle is
returned.

`record_create` reutiliza el mismo proposal → preview → approval → commit →
verification. Su preview contiene requested values, no inventa un before/after
para defaults aún no materializados y nunca llama ORM `create`. El target sólo
contiene el model; el nuevo record ID procede exclusivamente del commit/receipt
Odoo.

`business_action` reutiliza el mismo boundary. En M6 el único action ID válido
es `sale.order.confirm.v1`, sin parámetros libres: la preview relee nombre y
estado, y el handler host-controlled invoca directamente `action_confirm()`.
No existe resolución dinámica de model/method ni tool de ejecución para Codex.

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

En create, el commit y el receipt idempotente se guardan en la misma
transacción Odoo. Un timeout post-commit se reconcilia por `attempt_id` y
verification recupera el ID original sin repetir `create`.

La confirmación curada usa la misma garantía transaccional: el receipt se
completa con el cambio de estado y un retry del mismo intento recupera el
resultado original sin volver a ejecutar la acción.

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

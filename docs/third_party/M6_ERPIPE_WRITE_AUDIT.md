# M6 ERPipe safe-write audit

Audit date: 2026-08-23.

Source reviewed: `erpipe-org/mcp-odoo`, commit
`f724f97590b9bbe71cb50e59ed68ce94aeb9769e`, MIT license (copyright 2025
Lê Anh Tuấn). Relevant files were `src/odoo_mcp/agent_tools.py`,
`src/odoo_mcp/tools_write.py`, `src/odoo_mcp/server_core.py`,
`src/odoo_mcp/write_policy.py`, `src/odoo_mcp/audit.py` and their tests.

## Useful patterns

- deterministic JSON serialization before hashing an approval payload;
- validation against non-empty live `fields_get` metadata;
- a separate preview/validate/execute sequence;
- expiry and single-process consumption of approval records;
- audit entries store a token digest rather than the token itself;
- direct CRUD through the generic method path is rejected.

## Gaps against this repository's Source of Truth

- approvals are process-local rather than durable PostgreSQL state;
- the approval is not bound to Odoo uid, companies, turn, policy revision or
  the observed precondition;
- the surface includes create/unlink, multi-record writes, caller context and
  a generic `execute_method`, all outside the first M6 slice here;
- the token is a deterministic payload digest, not a distinct short-lived
  ACTION authority with replay protection;
- execution calls the external Odoo method directly and does not revalidate
  through this addon's current-user boundary;
- the JSONL audit is optional/fail-open and there is no mandatory post-write
  re-read verification.

## Reuse decision

No donor code is copied. M6 independently implements the small conceptual
patterns above using this repository's strict Pydantic contracts, Assistant
PostgreSQL, Odoo-side signed authorities, effective-user ORM environment and
mandatory verification/audit flow. This avoids importing ERPipe's broader MCP
surface and preserves the architecture and security invariants already fixed
for this product.

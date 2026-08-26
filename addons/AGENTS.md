# Addon development rules

This tree contains the current product runtime.

- Odoo 18 Community is the host and authority.
- Browser traffic terminates at Odoo; do not add a browser-to-sidecar path.
- Business access uses the effective user Environment with `su=False`, ACLs, record rules, field access and active companies.
- Reuse `AgentTurnService`, the Odoo-native turn queue/events, `CapabilityRegistry` and `CapabilityExecutor` before adding new infrastructure.
- Do not expose arbitrary SQL, Python, shell, sudo or unrestricted ORM method calls to the model.
- Writes must remain host-validated and use the existing preview/policy/approval/verification lifecycle where applicable.
- Codex remains an ephemeral provider subprocess; provider credentials stay below the effective Odoo `data_dir` and out of PostgreSQL/prompts/logs.
- Settings/Diagnostics/account-management surfaces are administrator-gated.

For architecture, read `docs/CURRENT_STATE.md`, `docs/ARCHITECTURE.md`, ADR-016, ADR-017 and ADR-018. External project patterns are references only.
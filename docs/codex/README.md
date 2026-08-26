# Codex documentation

Codex App Server is the current reasoning-provider adapter for the embedded Odoo runtime. It runs as an ephemeral local subprocess under the Odoo operating-system identity; it is not the product's operational host or a standalone Assistant Service.

## Current documents

- [`CODEX_AUTH.md`](CODEX_AUTH.md) — provider-owned account lifecycle, `CODEX_HOME`, device-code login and database activation.
- [`../CURRENT_STATE.md`](../CURRENT_STATE.md) — audited implementation snapshot.
- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — product/runtime boundaries.
- [`../UNIFIED_AGENT_RUNTIME.md`](../UNIFIED_AGENT_RUNTIME.md) — turn/reasoning/execution lifecycle.
- [`../CAPABILITY_FRAMEWORK.md`](../CAPABILITY_FRAMEWORK.md) — current tool/capability contract.

## Historical material

The `M*.md` files in this directory, `tasks/`, `exec-plans/` and `MILESTONES.md` are retained as implementation chronology/task evidence from earlier stages. They are not active milestone instructions and do not override current code/ADRs/docs.

In particular, references to a standalone Assistant Service, old routing milestones, service APIs, separate Assistant DB or instructions such as “do not start the next milestone” are historical context only.

See [`../HISTORICAL_DOCUMENTATION.md`](../HISTORICAL_DOCUMENTATION.md).

## Current integration rules

- Odoo owns identity, persistence, scheduling, policy and capability execution.
- Codex receives only the context/capabilities exposed by the host for the turn.
- Provider credentials remain in private `CODEX_HOME` below Odoo `data_dir` and are not copied into PostgreSQL/prompts/logs.
- The host validates every requested capability/effect; provider output never grants authority.
- Provider/runtime failures are sanitized before reaching the browser.

When changing the Codex adapter, inspect current code and protocol behavior first; milestone documents are evidence, not specifications.
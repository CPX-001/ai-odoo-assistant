# Odoo AI Assistant

AI assistant embedded in Odoo 18 Community. The current product is an Odoo-native agent runtime: Odoo owns identity, permissions, persistence, scheduling, policy and execution, while Codex App Server is launched ephemerally as the reasoning provider.

## Current architecture

```text
OWL assistant panel / Odoo RPC
            |
            v
Odoo controllers + conversation models
            |
            v
odoo.ai.turn + persisted events + ir.cron
            |
            v
AgentTurnService / ReasoningEngine
            |
            +--> CapabilityRegistry -> effective catalog
            |         |
            |         +--> odoo_query
            |         +--> odoo_actions
            |         +--> odoo_batch
            |         +--> odoo_runtime
            |
            +--> Codex App Server (ephemeral subprocess)
            |
            v
CapabilityExecutor / policy / approval / verification
            |
            v
Effective Odoo Environment (su=False)
```

There is no product-required FastAPI/Uvicorn Assistant daemon, internal service port, second operational database or shared machine secret. The historical `service/` and `installer/` trees are retained only as lineage/regression evidence.

## Security and authority

- Business operations use the authenticated Odoo user's Environment, allowed companies, ACLs, record rules and field access.
- `CapabilityDefinition` owns the executable contract: JSON schemas, risk/effect metadata, approval semantics, guards, budgets and handler.
- Reasoning does not grant authority. The host revalidates calls before execution.
- Writes follow host-controlled prepare/preview/policy-or-approval/execute/verify semantics.
- Codex credentials are provider-owned in a private `CODEX_HOME` below Odoo's effective `data_dir`; token material is not copied into Odoo PostgreSQL.
- A database-scoped non-secret activation gate controls whether that database may use the installation-scoped Codex account.

## Current product surface

The addon provides the floating assistant panel, persistent conversations/turns, screen context, runtime account connection through Settings, policy/autonomy settings, diagnostics, query/discovery capabilities, bounded CRUD/action capabilities, batch capabilities and durable turn processing.

The current core provider package contains `odoo_actions`, `odoo_batch`, `odoo_query` and `odoo_runtime`. General document RAG, first-class configurable Skills/Bundles, an external `CapabilityProvider` extension API, automations/AI fields, MCP exposure, governed memory and multimodal attachments are product directions, not current completed features.

## Install and configure

1. Add this repository's `addons` directory to Odoo's `addons_path`.
2. Update the Apps list and install **Odoo AI Assistant**.
3. Ensure the Codex executable is available to the Odoo OS user. An explicit executable can be stored in `odoo_ai_assistant.codex_executable` when required.
4. Open Odoo Settings and connect the Codex account using the official device-code flow.
5. Configure maximum agent autonomy/risk policy in Settings as needed.

Mutable runtime state is created under:

```text
<data_dir>/odoo_ai_assistant/
  codex/
  runtime/
  cache/
  source/
```

These directories are owned by the Odoo runtime identity and tightened to mode `0700` by the addon.

## Documentation

Start at [`docs/README.md`](docs/README.md). It distinguishes current documentation from historical milestone material.

Primary current documents:

- [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) — audited implementation snapshot.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — current architecture and boundaries.
- [`docs/UNIFIED_AGENT_RUNTIME.md`](docs/UNIFIED_AGENT_RUNTIME.md) — agent/turn lifecycle.
- [`docs/CAPABILITY_FRAMEWORK.md`](docs/CAPABILITY_FRAMEWORK.md) — capability contracts and extension direction.
- [`docs/DEPLOYMENT_CONFIG.md`](docs/DEPLOYMENT_CONFIG.md) — deployment/configuration.
- [`docs/codex/CODEX_AUTH.md`](docs/codex/CODEX_AUTH.md) — Codex authentication lifecycle.
- [`docs/adr/`](docs/adr/) — accepted architecture decisions.
- [`docs/DOCUMENTATION_AUDIT.md`](docs/DOCUMENTATION_AUDIT.md) — 2026-08-26 repository-wide documentation close-out checkpoint.

The research PDFs in `docs/source-of-truth/` are dated reference material. They intentionally do not override newer code or ADRs. Old milestone/task documents and the retained `service/`, `installer/` and root `migrations/` trees are explicitly classified as historical and are not the current backlog or deployment path.

## Development and tests

Current product changes should be validated primarily against addon/runtime tests and an Odoo 18 installation. Sidecar-era `service/`, installer and milestone E2E tests remain useful only when the change explicitly touches preserved legacy/regression code.

When model behavior is part of the acceptance criteria, deterministic tests are necessary but not sufficient: add scenario/eval coverage for tool choice, grounding, permissions and write safety.

See [`tests/AGENTS.md`](tests/AGENTS.md) for test guidance.

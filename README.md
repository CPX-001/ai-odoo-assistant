# Odoo AI Assistant

Odoo AI Assistant is an Odoo 18 Community addon with an Odoo-native chat panel,
embedded turn queue, typed capabilities and an ephemeral Codex App Server reasoning
adapter. Odoo remains authoritative for identity, ACLs, record rules, schemas, policy,
approval, execution and verification.

The supported operational shape is a normal addon:

```text
Owl / RPC
    -> Odoo controllers and models
        -> odoo.ai.turn + ir.cron
        -> embedded AgentTurnService
        -> typed capabilities under the real user (su=False)
        -> ephemeral Codex App Server subprocess
```

There is no required FastAPI/Uvicorn sidecar, second daemon, Assistant database,
machine shared secret or extra internal port. Mutable runtime data is created below the
effective Odoo `data_dir` and uses the operating-system identity of the Odoo process.

## Install

1. Place this repository in an Odoo custom-addons location, or add its `addons/`
   directory to `addons_path`.
2. Update the Apps list.
3. Install **Odoo AI Assistant**.
4. Configure Codex and the Assistant policy in **Settings -> AI Assistant**.

Codex is the only planned host-level runtime dependency. The addon discovers it from
the Odoo service `PATH` or an administrator override and does not download binaries.

## Verification

```bash
python -m compileall service/src tests addons/odoo_ai_assistant
cd service
python -m pytest
python -m ruff check src ../tests ../installer ../addons/odoo_ai_assistant
python -m mypy src/odoo_ai
```

The Odoo gate installs and upgrades the addon with Odoo 18 using
`--test-enable --test-tags /odoo_ai_assistant` under the normal Odoo Unix user.

The current architecture is defined by
[`docs/adr/ADR-016-embedded-odoo-runtime.md`](docs/adr/ADR-016-embedded-odoo-runtime.md)
and [`docs/adr/ADR-017-addon-capability-framework.md`](docs/adr/ADR-017-addon-capability-framework.md).
The Source of Truth v1.0 remains normative where later accepted ADRs and the v1.1
amendment do not supersede it.

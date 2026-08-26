# Retired Assistant-database migrations

The root `migrations/` tree and root `alembic.ini` belong to the former standalone Assistant Service database.

They are **not** the schema migration mechanism for the current embedded product. Operational persistence now lives in Odoo models/PostgreSQL plus addon lifecycle/migration hooks under `addons/odoo_ai_assistant/` when needed.

Keep these Alembic files only as historical/regression evidence for the retired `service/` lineage. Do not create new current-product persistence here or reintroduce a second Assistant database without a new architecture decision.

Current references: `../docs/CURRENT_STATE.md`, `../docs/ARCHITECTURE.md`, `../docs/DEPLOYMENT_CONFIG.md` and ADR-016.

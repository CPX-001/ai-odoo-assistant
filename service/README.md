# Retired Assistant Service

This directory preserves the former standalone Assistant Service implementation (FastAPI/SQLAlchemy/Alembic/PostgreSQL lineage).

It is **not** part of the supported operational architecture after ADR-016. Current product turns, conversations, scheduling, policy and capability execution live in the Odoo addon.

Do not use this tree to infer current deployment requirements such as:

- a FastAPI/Uvicorn daemon;
- a dedicated Assistant HTTP port;
- a second operational PostgreSQL database;
- an Odoo↔Assistant shared machine secret;
- sidecar-owned conversation/retrieval persistence.

The code is retained for audit, regression and as a source of patterns that may be deliberately ported into the embedded runtime. Any revived feature must be redesigned against current code/ADRs rather than reconnecting this service by default.

Current entry points: `../README.md`, `../docs/README.md`, `../docs/CURRENT_STATE.md`, `../docs/ARCHITECTURE.md` and local `AGENTS.md`.

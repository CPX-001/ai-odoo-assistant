# Retired Assistant Service lineage

`service/` is not the current product runtime. It contains the former FastAPI/SQLAlchemy/PostgreSQL Assistant Service implementation and tests retained for historical, audit and regression value after ADR-016 moved the operational runtime into Odoo.

Rules:

- Do not add new product features here unless the user explicitly requests work on the retired lineage.
- Do not make current addon code depend on this service.
- Do not use sidecar ports, service URLs, shared machine secrets or the former Assistant DB as current deployment requirements.
- If a useful old feature is revived, redesign/port it through the embedded addon runtime and current Capability Framework rather than reconnecting the sidecar by default.
- Historical tests may remain unchanged when they are evidence of the old implementation; they do not prove current embedded-runtime behavior.

Current sources: `docs/CURRENT_STATE.md`, `docs/ARCHITECTURE.md`, ADR-016 and ADR-017.
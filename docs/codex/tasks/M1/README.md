# Historical M1 task-packet index

> Archive notice: this directory records the former M1 runtime/install milestone. It describes the retired standalone Assistant Service deployment and must not be used as current installation guidance.

Historically, M1 established the FastAPI/SQLAlchemy service, its separate Assistant PostgreSQL database, bootstrap/systemd flow and related gates. ADR-016 later retired that operational architecture in favor of the embedded Odoo runtime.

The task packets remain unchanged as audit/regression evidence. Their service ports, Assistant DB, systemd, bootstrap and milestone sequencing are historical.

Current replacements:

- deployment: `../../../DEPLOYMENT_CONFIG.md`;
- implementation state: `../../../CURRENT_STATE.md`;
- architecture: `../../../ARCHITECTURE.md` and ADR-016;
- current product code: `../../../../addons/odoo_ai_assistant/`.

The parent archive policy is `../README.md`.

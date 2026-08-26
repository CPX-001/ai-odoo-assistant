# Retired installer lineage

`installer/` belongs to the former deployment that provisioned a separate Assistant Service. It is not the supported current product deployment after ADR-016.

Rules:

- Do not introduce or restore a product-required sidecar daemon, service port, second Assistant PostgreSQL database or shared machine secret from this tree.
- Do not extend systemd/supervisor sidecar provisioning as the normal installation path.
- Preserve existing files only for historical/audit/regression value unless an explicit cleanup task removes them.
- New deployment work belongs to the Odoo addon/host and must follow `docs/DEPLOYMENT_CONFIG.md`.

If a future external service becomes necessary, justify it with a new architecture decision rather than treating this installer as current.
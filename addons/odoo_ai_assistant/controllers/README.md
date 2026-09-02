# Controllers

The supported browser/API surface terminates in Odoo and uses Odoo-authenticated
identity. Controllers translate transport input into model/service calls; they do
not own capability authority, policy or provider credentials.

Current modules:

- `chat_bridge.py` — authenticated chat/conversation bridge.
- `turn_runtime.py` and `turn_live.py` — durable turn submission/state projection.
- `turn_control.py` — stop/redirect and related live controls.
- `chat_history_actions.py` — authenticated conversation history operations.
- `activity_preferences.py` — user-owned activity display preferences.
- `public_references.py` — bounded public-reference resolution under Odoo access.

## Removed sidecar callback

The retired `internal_tools.py` route
`/odoo_ai/internal/v1/instance-inventory` is not part of the embedded product and
has been removed. No Odoo AI Assistant controller may use `auth="none"`.
Installation inventory is now consumed internally through the P8 Evidence
provider and never through a machine-secret HTTP callback.

The boundary is locked by `tests/unit/test_phase8_supported_surface.py` and the
existing addon-boundary tests. Adding a new route requires authenticated identity,
input bounds, access checks and a current documentation update.

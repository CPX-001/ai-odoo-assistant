# Phase 2 deterministic fault addon

Test-only Odoo 18 fixture for the five Phase 2 real presentation gates. It is outside the product
addon path and is inert unless the Odoo process has `ODOO_AI_PHASE2_FAULT_FIXTURE=1` **and** the
database name starts with `odoo_ai_`.

Exact user messages arm one failure on the real persisted turn/cron/browser path:

- `__P2_REAL_AUTH__`
- `__P2_REAL_ACL__`
- `__P2_REAL_TIMEOUT__`
- `__P2_REAL_TOOLFAIL__`
- `__P2_REAL_RECOVERY__`

The ACL case performs a real ORM read under the originating `su=False` user against a fixture model
readable only by `base.group_system`. The recovery case persists only the test turn's write barrier
before raising; it does not commit a business effect. Do not install this fixture on non-disposable
databases.

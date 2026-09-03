# Odoo AI Assistant addon

The supported product is an Odoo 18 Community addon with an embedded durable agent
runtime. The browser talks to authenticated Odoo routes; Codex App Server is an
ephemeral reasoning-provider subprocess rather than a product daemon.

## Product and authority

The customer installs one Odoo AI Assistant application. Chat remains available from
the systray; Knowledge, Diagnostics and Configuration are exposed through Odoo menus.
Public profiles are exactly `user` and `technical`.

Odoo owns identity, persistence, ACLs, record rules, companies, capability authority,
policy/approval, effect plans, execution, verification and recovery. Business writes
use the effective user Environment with `su=False`. The model proposes but cannot grant
itself authority.

`runtime/capabilities/` provides the common `CapabilityDefinition`, provider, Skill,
Context and Evidence extension framework. There is no arbitrary SQL, Python, shell,
sudo or unrestricted ORM-method tool.

## Evidence and Knowledge

P8 provides bounded installation Evidence from runtime, source/XML and configured logs.
P9 adds Odoo-native company Knowledge with bounded ingestion, PostgreSQL lexical FTS,
company/private access, citations and stale-version revalidation. Retrieved/file text
is untrusted data and cannot alter policy.

## P10 Technical/host operations — accepted

Accepted Technical capabilities include:

```text
odoo.module.inspect
postgres.health
odoo.config.inspect
odoo.config.patch
host.service.status
host.service.restart
odoo.module.update
```

Broker-backed effects use the accepted ADR-024 AF_UNIX privilege boundary with exact
logical targets, `SO_PEERCRED`, bounded requests/receipts, fixed argv, durable replay
state and explicit uncertainty. Module update uses the external lifecycle-safe
maintenance adapter. P10 is accepted through
`bde508b737c132140e237cdfde31aee9b37eca5f`.

## P11 durable CSV workflows — implemented, validation pending

The addon currently depends on Odoo's standard `base_import` and implements:

```text
odoo.ai.data.import.session
odoo.ai.data.import.chunk

assistant.data_import.inspect_csv
assistant.data_import.start_csv
assistant.data_import.status
assistant.data_import.inspect_cleanup
assistant.data_import.start_clean_csv
assistant.data_import.inspect_rejected
assistant.data_import.resume_csv
```

The host binds a current-turn CSV to an eligible model and direct writable scalar
mapping, stages the mapped rows once, fingerprints the artifact/mapping/staged state
and executes one bounded chunk per cron transaction under the originating user.
Committed rows, cursor advance and the completed receipt share one transaction; a
committed chunk is not blindly replayed.

Native validation errors roll back the current chunk and create a historical rejected
receipt. The model may propose only finite deterministic cleanup of already-mapped
fields (`trim`, `normalize_whitespace`, `replace_exact`, `set_if_empty`). Changed rows
count as `corrected_rows` only after successful commit.

A rejected chunk can be inspected through a bounded mapped-field view and explicitly
repaired with `row + mapped field + replacement value`. Resume retains earlier
completed chunks and the rejected receipt, advances a repair revision/fingerprint and
retries from the unchanged committed cursor with a new receipt sequence.

P11 remains create-only CSV. Spreadsheet formats, relational import paths, external-id
upsert/update and arbitrary transformation scripts are not claimed.

## Current validation truth

```text
P0-P10 COMPLETE / ACCEPTED
P11 ADVANCED IMPORTS CSV CORE IMPLEMENTED
P11 focused static/module/Odoo gates NOT EXECUTED
P11 six HARD real gates NOT EXECUTED
P11 NOT ACCEPTED
```

Prepared focused P11 classes:

```text
TestPhase11DataImportSession                 4 methods
TestPhase11DataImportCleanupRepair           4 methods
```

Use:

```text
docs/CURRENT_STATE.md
docs/research/EXECUTION_STATE.md
docs/research/P11_ADVANCED_IMPORTS_FIRST_SLICE.md
docs/research/P11_IMPORT_CLEANUP_REPAIR_SLICE.md
docs/research/P11_FOCUSED_VALIDATION_RUNBOOK.md
```

No committed code or prepared test should be reported as PASS until the corresponding
gate actually executes.

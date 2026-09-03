# Odoo AI Assistant

Odoo AI Assistant is an Odoo 18 Community addon with a durable provider-neutral agent
host embedded in Odoo. Odoo remains identity, persistence, permission, policy and
execution authority; the reasoning model proposes work through typed host contracts.

## Current state

```text
P0-P11 COMPLETE / ACCEPTED
P11 accepted through 72b4b826bddffc20f99f5cd72f14ed95111eab5c
P12.1 BOUNDED SOURCE WORKSPACES FOCUSED ACCEPTED
P12.2 TYPED PATCH/DIFF IMPLEMENTED / FOCUSED VALIDATION PENDING
P12 NOT ACCEPTED
```

A post-P11 spreadsheet/chat import extension is also implemented and awaiting focused
validation. The exact cursor is
[`docs/research/EXECUTION_STATE.md`](docs/research/EXECUTION_STATE.md).

## Architecture

```mermaid
flowchart TB
    UI[OWL chat / Odoo surfaces] --> TURN[Durable Odoo turn]
    TURN --> HOST[Provider-neutral host loop]
    HOST <--> MODEL[Codex App Server adapter]
    HOST --> CAPS[Capabilities + Skills + Context + Evidence]
    CAPS --> ORM[Effective Odoo Environment, su=False]
    HOST --> EFFECT[Preview / policy / approval / execute / verify]
    EFFECT --> ORM
    EFFECT --> BROKER[Optional finite P10 host broker]
    SRC[Installed addon source] --> WS[P12 private source workspace]
    WS --> PATCH[P12.2 typed derived workspace + diff receipt]
    PATCH -. P12.3 test receipt .-> TEST[Tested fingerprint]
    TEST -. P12.4 managed deploy .-> EFFECT
```

`CapabilityDefinition` is the atomic executable contract. Skills, Evidence, attachments
and model text never grant permissions. There is no arbitrary SQL, Python, shell,
sudo, Git command or unrestricted Odoo method surface.

Public product profiles are exactly `user` and `technical`; autonomy is independent
from technical reach.

## Evidence, Knowledge and imports

P8/P9 provide bounded installation Evidence and Odoo-native company Knowledge. P11
provides durable create-only imports through mapped-row staging, bounded background
chunks, exact receipts and no-blind-replay recovery.

The chat paperclip now accepts temporary `CSV`, `XLS`, `XLSX` and `ODS` artifacts for
structured imports. Spreadsheet parsing is delegated to Odoo `base_import`, then the
accepted P11 staging/chunk machinery continues unchanged. Spreadsheet attachments do
not automatically become Company Knowledge.

Format-neutral import capabilities are:

```text
assistant.data_import.inspect_file
assistant.data_import.start_file
```

The older CSV capability ids remain available for compatibility. Spreadsheet breadth
is implemented but not yet recorded PASS; see
[`docs/research/P11_SPREADSHEET_CHAT_IMPORT_EXTENSION.md`](docs/research/P11_SPREADSHEET_CHAT_IMPORT_EXTENSION.md).

## P10 Technical host boundary

Accepted Technical operations use ADR-024's optional finite AF_UNIX broker for managed
configuration/service/module maintenance instead of a general root shell. Host effects
retain preview, policy, durable binding, verification and explicit uncertainty.

## P12 controlled source modification

ADR-025 makes source work **workspace-first**. Host code resolves an installed module
to its exact source root and copies a bounded snapshot into a private logical
workspace. The model never chooses an absolute filesystem path.

P12.1's source/workspace authority gate is accepted. P12.2 now adds Technical-only
workspace capabilities for bounded logical file reads, deterministic patch preview and
policy-controlled patch application. Patch input supports only typed create/delete or
exact old->new text replacement. Preview returns the complete bounded unified diff and
exact before/after/diff/approval fingerprints.

Applying a patch does **not** edit production source and does not mutate the parent
workspace. It creates a new derived private workspace and a path-free receipt binding
parent, child, user/turn authority and fingerprints. P12.3 must test that exact staged
fingerprint before P12.4 can separately cross the managed production deployment
boundary.

See:

- [`docs/adr/ADR-025-controlled-source-workspaces.md`](docs/adr/ADR-025-controlled-source-workspaces.md)
- [`docs/research/P12_SOURCE_WORKSPACE_FOUNDATION.md`](docs/research/P12_SOURCE_WORKSPACE_FOUNDATION.md)
- [`docs/research/P12_PATCH_DIFF_CONTRACT.md`](docs/research/P12_PATCH_DIFF_CONTRACT.md)
- [`docs/research/P12.2_FOCUSED_VALIDATION_RUNBOOK.md`](docs/research/P12.2_FOCUSED_VALIDATION_RUNBOOK.md)

## Validation

P11 is accepted on immutable evidence. P12.1 compile/Ruff, 10 dependency-light tests
and 3 focused Odoo methods are PASS on its recorded evidence. P12.2 and the new
spreadsheet/chat path have prepared focused tests but **no PASS claim yet**.

The remaining Phase-12 real gates cover path authority, diff approval,
test-before-deploy, deploy verification and failed-deploy recovery.

## Installation

Add the repository `addons` directory to the Odoo 18 addons path and install
`odoo_ai_assistant` normally. Provider credentials remain in host-owned `CODEX_HOME`,
not PostgreSQL, prompts or source workspaces. Deploy `host_broker/` only when the finite
Technical host operations are required.

Read [`AGENTS.md`](AGENTS.md) before architecture changes. The documentation entry point
is [`docs/README.md`](docs/README.md).

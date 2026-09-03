# Current implementation state

This is the current-state entry point for the supported Odoo 18 product on `main`.
For the exact roadmap cursor and validation truth use
[`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md).

## Accepted lineage

```text
P0-P11 COMPLETE / ACCEPTED
P11 accepted through 72b4b826bddffc20f99f5cd72f14ed95111eab5c
P12.1 BOUNDED SOURCE WORKSPACES FOCUSED ACCEPTED
P12.2 TYPED PATCH/DIFF IMPLEMENTED / FOCUSED VALIDATION PENDING
P12 NOT ACCEPTED
```

P11 remains the latest fully accepted phase. P12.1 is an accepted Phase-12 authority
foundation. P12.2 code exists but is not PASS evidence until its focused gate executes.

## Product baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Supported addon: `addons/odoo_ai_assistant`.
- Current addon version: `18.0.13.37.0`.
- Dependencies: `account`, `base`, `base_import`, `sale`, `web`.
- Runtime is embedded in Odoo; the browser talks only to authenticated Odoo routes.
- Business capabilities execute under the effective Odoo user with `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Codex App Server is the current ephemeral reasoning provider, not product authority.
- No arbitrary SQL, Python, shell, sudo, Git command or unrestricted ORM-method surface
  is exposed.

Product-facing human profiles remain exactly `user` and `technical`. Autonomy cannot
create Odoo permissions or enlarge host/filesystem authority.

Capability handlers now execute behind an effective-user savepoint that restores the
Odoo cursor before structured failure/recovery handling. Bulk deletion declares
`continue_on_error`: it keeps protected contacts, isolates ordinary per-record Odoo
or database rejections, verifies the resulting applied/excluded/failed scope and gives
the post-effect agent a bounded partial receipt. The browser keeps TaskPlan exclusive
to explicit Plan turns, follows approved operations automatically and lets terminal
turn state override stale execution projections; manual status inspection is reserved
for genuinely uncertain recovery.

Turn state, approval, the write barrier and EffectJournal are authoritative; event
history and live activity are derived projections. Authoritative writes are flushed
before an optional event attempt, state-asserting live activity is published only
after commit, and an event-store failure cannot orphan a scheduler claim or undo
approval, cancellation, recovery or reversion. Verified incomplete outcomes close
immediately with host-grounded exact counts, and the verified receipt compacts old
working context when necessary so finalization retains bounded transcript headroom.

Natural-language model discovery normalizes Unicode and ranks close lexical inflections
against the live Odoo registry before applying effective-user access checks. Requests
such as `contacts` or `contactos` therefore resolve the installed `Contact` model
without a hardcoded business-alias table, while unrelated terms still return no model.

## Durable agent, Evidence and Knowledge

Accepted P5-P7 provide durable turns, concurrency/recovery, TaskPlan vs EffectPlan,
EffectJournal, interventions, provider-neutral decisions and the installed-addon
Capability/Skill/Context/Evidence extension framework.

Accepted P8 provides bounded provenance/freshness/access-aware runtime, source/XML and
log Evidence. Accepted P9 provides Odoo-native company Knowledge with bounded document
ingestion, PostgreSQL lexical FTS, citations and stale-reference handling. Retrieved or
uploaded content is untrusted data and cannot grant executable authority.

## Accepted P10 Technical/host operations

Technical operations include module inspect/update, PostgreSQL health, managed config
inspect/patch and service status/restart. ADR-024 governs the optional AF_UNIX broker
with deployment-owned logical targets, peer credentials, fixed argv, durable effect
receipts and explicit uncertainty. It is not a general shell or Assistant sidecar.

## Accepted P11 advanced imports plus post-acceptance spreadsheet breadth

The accepted P11 evidence proves durable create-only CSV import, mapped-row staging,
bounded background chunks, exact receipts, no-blind-replay recovery, deterministic
cleanup and rejected-window repair/resume.

A post-acceptance product-path fix now additionally lets the chat paperclip carry
short-lived tabular artifacts:

```text
CSV / XLS / XLSX / ODS
```

The reason for this extension is concrete: the chat uploader still inherited P9's
Knowledge document allowlist, so Excel could not reach the P11 workflow. Spreadsheet
artifacts are now temporary turn-bound files; they are not automatically indexed into
Company Knowledge. Native preparation delegates workbook parsing to Odoo `base_import`,
then reuses the same P11 staged-row/chunk/receipt execution.

Format-neutral capability aliases are now present:

```text
assistant.data_import.inspect_file
assistant.data_import.start_file
```

The original CSV ids remain compatible. This spreadsheet breadth is **validation
pending** and does not retroactively alter the immutable P11 acceptance evidence. See
`research/P11_SPREADSHEET_CHAT_IMPORT_EXTENSION.md`.

## P12.1 controlled source workspace — focused accepted

ADR-025 establishes a workspace-first source-modification boundary. A bounded installed
addon snapshot is copied beneath the Assistant runtime source workspace using a
host-generated logical id. Physical paths remain host-internal.

The P12.1 contract includes:

```text
source_id = odoo-addon:<module>
workspace_id = workspace:v1:<32hex>
private 0700 directories / 0600 files
no followed symlinks
no source/workspace-root overlap
4096 file ceiling / 64 MiB total / 8 MiB per file
deterministic source/workspace SHA-256 fingerprints
source-stale vs workspace-changed state
uid/company/database-hash/turn binding
path-free public metadata
```

Formal P12.1 focused validation passed on the recorded evidence at
`research/evidence/phase12/2026-09-03/P12.1-FOCUSED-ad1378b.md`.

## P12.2 typed patch/diff — implemented, validation pending

P12.2 promotes the private workspace through the existing capability framework without
creating an arbitrary filesystem editor.

Current capabilities:

```text
assistant.source_workspace.prepare
assistant.source_workspace.inspect
assistant.source_workspace.read_file
assistant.source_workspace.preview_patch
assistant.source_workspace.apply_patch
assistant.source_workspace.inspect_patch
```

`apply_patch` is Technical-only PLAN/ACTION/POLICY. Input is a bounded structured edit
contract over logical paths only:

```text
modify -> exact old fragment + replacement
create -> bounded UTF-8 content
delete -> logical path
```

The host requires an exact current workspace fingerprint. A modify fragment must match
exactly once. Path traversal, absolute paths, VCS/runtime/secret paths, binary files and
unsupported suffixes fail closed.

Preview computes and exposes the complete bounded unified diff plus:

```text
before workspace fingerprint
after workspace fingerprint
diff fingerprint
approval fingerprint
```

A diff larger than the approval ceiling is rejected instead of silently truncated.
Applying the patch revalidates the proposal and creates a **new derived private
workspace**; the parent remains unchanged. A private receipt binds parent/child,
binding, changed logical paths and all fingerprints. Installed source is still not
modified.

P12.2 therefore stops at `workspace -> approved derived workspace`. P12.3 must bind
actual tests to that exact after-workspace fingerprint. P12.4 must separately implement
managed deploy, verification and recovery.

## Validation truth

```text
P11 accepted CSV focused + six real gates                 PASS (immutable evidence)
post-P11 XLSX/chat regression                             NOT EXECUTED
P12.1 compile/Ruff + 10 unit + 3 Odoo methods            PASS
P12.2 SourcePatchTests                                   NOT EXECUTED — 9 prepared
P12.2 TestPhase12SourcePatch                             NOT EXECUTED — 3 prepared
P12.2 direct P12.1 Odoo neighbor rerun                   NOT EXECUTED
P12-REAL-PATH-BOUNDARY                                   NOT EXECUTED
P12-REAL-DIFF-APPROVAL                                   NOT EXECUTED
P12-REAL-TEST-BEFORE-DEPLOY                              BLOCKED — P12.3 missing
P12-REAL-DEPLOY-VERIFY                                   BLOCKED — P12.4 missing
P12-REAL-FAILED-DEPLOY-RECOVERY                          BLOCKED — P12.4 missing
P12 acceptance                                           NOT COMPLETE
```

Use `research/P12.2_FOCUSED_VALIDATION_RUNBOOK.md`. The next implementation phase is
P12.3 only after the focused P12.2 authority gate is green and any applicable real
diff-approval gate is resolved.

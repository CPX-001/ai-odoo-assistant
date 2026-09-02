# P8 focused validation runbook

State: `PREPARED / NOT EXECUTED`  
Scope: P8.0 hardening plus P8.1/P8.2 Evidence foundation

This runbook is intentionally focused. It does not authorize the full repository,
Product Behavior FULL, browser or real-provider regression unless a failure proves
that wider scope is necessary or the execution cursor is explicitly updated.

## 1. Load the exact remote state

```text
git fetch origin
git checkout main
git pull --ff-only origin main
git status --short --branch
```

Read:

```text
AGENTS.md
docs/research/EXECUTION_STATE.md
docs/research/P8_EVIDENCE_CORE_IMPLEMENTATION.md
docs/EVIDENCE_ARCHITECTURE.md
docs/adr/ADR-022-evidence-core-and-ledger.md
```

Do not run against an older local checkout and do not overwrite newer main work.

## 2. Static/import boundary

Run the repository's normal focused formatting/lint/compile commands for the changed
Python files. At minimum compile/import:

```text
addons/odoo_ai_assistant/runtime/capabilities/evidence.py
addons/odoo_ai_assistant/runtime/capabilities/evidence_runtime.py
addons/odoo_ai_assistant/runtime/capabilities/runtime_evidence.py
addons/odoo_ai_assistant/runtime/capabilities/provider.py
addons/odoo_ai_assistant/runtime/capabilities/extensions.py
addons/odoo_ai_assistant/controllers/__init__.py
```

Fail on syntax errors, import cycles, unsupported Python syntax for the repository's
runtime, lint violations or an import that requires a live Odoo registry in the
dependency-light suite.

## 3. Dependency-light focused tests

Run:

```text
python -m pytest -q \
  tests/unit/test_phase8_evidence_contracts.py \
  tests/unit/test_phase8_evidence_runtime.py \
  tests/unit/test_phase8_extension_evidence.py \
  tests/unit/test_phase8_supported_surface.py
```

Then run directly affected P7 tests selected from the current tree for:

```text
CapabilityProvider construction/discovery/composition
optional-provider failure isolation
Skill evidence-provider selectors
ContextProvider activation
EffectiveAssistantManifest evidence_provider_ids
Codex host-guidance versus untrusted-data partition
```

Do not guess filenames from this runbook; discover the current tests and record the
exact selection.

## 4. Focused Odoo gate

Use the existing disposable Odoo 18 Community test environment and repository addon
path. Install/update `odoo_ai_assistant`, then run the test containing:

```text
TestPhase8RuntimeInventoryEvidence
```

Also run the current addon-boundary tests affected by deleting the sidecar callback.
Required assertions:

- addon installs and updates cleanly;
- no Assistant route uses `auth="none"`;
- runtime inventory is collected from the effective Odoo Environment;
- the Assistant addon appears in the current installed-module projection;
- user/company/group access binding is rechecked on fetch;
- a mismatched fingerprint becomes explicit `stale`;
- no absolute path, credential or host command appears in public inventory output;
- P7 extension composition still works with an Evidence catalog present.

An access failure for an ordinary User profile is not silently repaired with an
unbounded `sudo()`. Decide at the host-fact boundary, add a targeted policy/ACL-safe
projection if required and test both User and Technical behavior.

## 5. Focused fixes

For any failure:

1. identify the owning contract rather than weakening the test;
2. preserve P7 authority and positional/source compatibility;
3. keep Evidence as untrusted data;
4. preserve limits and access recheck;
5. do not reintroduce the sidecar route/workflow;
6. rerun the smallest failing set plus its direct boundary.

No partial repair is reported as completion.

## 6. Required report

Create a dated record under:

```text
docs/research/evidence/phase8/YYYY-MM-DD/
```

Record:

```text
base and final main SHAs
environment/Odoo/Python versions
exact commands
exact test counts/outcomes
all repairs and reruns
unexecuted suites
affected P8 real gates (still NOT EXECUTED unless actually run)
```

Update `EXECUTION_STATE.md` only from actual evidence. A green focused gate changes
the slice to `FOCUSED_VALIDATED`; it does not accept P8.

## 7. Next implementation after green focused gate

Connect `AssistantEvidenceDecisionEngine` to the current provider-neutral live
decision path so model-driven turns can request, select and fetch Evidence, persist
the bounded ledger across reconnect and surface provenance/citations. Then prepare
the six named P8 real gates. Do not add a second agent/runtime or retrieval registry.

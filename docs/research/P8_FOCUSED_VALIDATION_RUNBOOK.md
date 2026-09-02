# P8 focused validation runbook

State: `PREPARED / NOT EXECUTED`  
Scope: reconciled P8.0 hardening plus P8.1/P8.2 Evidence foundation and first live Evidence projection

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
addons/odoo_ai_assistant/runtime/capabilities/contracts.py
addons/odoo_ai_assistant/runtime/capabilities/context.py
addons/odoo_ai_assistant/runtime/capabilities/skills.py
addons/odoo_ai_assistant/runtime/capabilities/features.py
addons/odoo_ai_assistant/runtime/capabilities/evidence.py
addons/odoo_ai_assistant/runtime/capabilities/evidence_runtime.py
addons/odoo_ai_assistant/runtime/capabilities/runtime_evidence.py
addons/odoo_ai_assistant/runtime/capabilities/provider.py
addons/odoo_ai_assistant/runtime/capabilities/registry.py
addons/odoo_ai_assistant/runtime/capabilities/extensions.py
addons/odoo_ai_assistant/runtime/capabilities/manifest.py
addons/odoo_ai_assistant/runtime/agent/extension_context.py
addons/odoo_ai_assistant/runtime/agent/codex_extension_context.py
addons/odoo_ai_assistant/controllers/__init__.py
tests/fixtures/odoo_addons/odoo_ai_assistant_p7_fixture/models/provider.py
```

Fail on syntax errors, import cycles, unsupported Python syntax for the repository's
runtime, lint violations or an import that unexpectedly requires a live Odoo registry
inside the dependency-light suite.

## 3. Dependency-light focused tests

Run:

```text
python -m pytest -q \
  tests/unit/test_phase8_evidence_contracts.py \
  tests/unit/test_phase8_evidence_runtime.py \
  tests/unit/test_phase8_extension_evidence.py \
  tests/unit/test_phase8_supported_surface.py \
  tests/unit/test_phase8_product_profiles.py \
  tests/unit/test_capability_provider_extensions.py \
  tests/unit/test_phase7_feature_negotiation.py \
  tests/unit/test_phase7_live_extension_context.py
```

Required assertions include:

```text
FrozenDict/FrozenList preserve dict/list compatibility but reject nested mutation
capability/context/Skill/provider metadata is copied and deeply immutable
capability guard exception -> unavailable
API-incompatible optional provider -> failed status, healthy sibling survives
reserved provider/resource namespace -> failed optional provider
missing dependency/cycle -> only attributable optional providers fail
Evidence optional guard/search/fetch failures are sanitized and isolated
Skill evidence selectors only see effective available Evidence IDs
generic/social queries do not trigger automatic Evidence retrieval
installation/how-to/diagnosis-shaped queries can route Evidence
live Evidence host metadata never contains retrieved prompt-injection text
retrieved Evidence remains untrusted_data in the Codex trust partition
public manifest values are user/technical, not business/developer
```

## 4. Focused Odoo gate

Use the existing disposable Odoo 18 Community test environment and repository addon
path. Install/update `odoo_ai_assistant` and the existing P7 fixture addon, then run at
least:

```text
TestPhase8RuntimeInventoryEvidence
TestPhase7Fixture
addon boundary tests for retired inventory/machine-auth surfaces
TestCanonicalPlanHostLoop
```

The fixture test at
`tests/fixtures/odoo_addons/odoo_ai_assistant_p7_fixture/tests/test_phase7_fixture.py`
is the installed-addon Evidence gate: it proves real Odoo-registry discovery,
CapabilityProvider composition, Skill selector activation, Evidence search/fetch,
fetch-time user scope rejection and manifest projection without editing core.

Required assertions:

- addon installs and updates cleanly;
- no Assistant route uses `auth="none"`;
- no supported addon machine-auth or inventory-service compatibility path remains;
- runtime inventory is collected in-process as `assistant.runtime_inventory` Evidence;
- the Assistant addon appears in the current installed-module projection;
- installed trusted addons can contribute an EvidenceProvider through the existing CapabilityProvider boundary;
- user/company/group access binding is rechecked on fetch;
- a mismatched fingerprint becomes explicit `stale`;
- no absolute path, raw database name, credential or host command appears in model-visible inventory output;
- P7 extension composition still works with an Evidence catalog present;
- immutable `CapabilityContext` metadata does not regress planning/effect behavior;
- public profile values are `user`/`technical` and remain descriptive only.

An access failure for an ordinary User profile is not silently repaired by adding a
generic `sudo()` path. If installation metadata needs a host-owned technical read,
implement a narrowly scoped host-fact adapter and test that it cannot expose business
records or expand user execution authority.

## 5. Focused fixes

For any failure:

1. identify the owning contract rather than weakening the test;
2. preserve P7 authority and source compatibility where still supported;
3. keep Evidence as untrusted data;
4. preserve limits and access recheck;
5. do not reintroduce sidecar route/workflow/machine-auth inventory paths;
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

The first provider-neutral live search/fetch/trust projection is already implemented.
After focused validation, continue with the smallest coherent next need demonstrated by
the real gates: durable ledger restoration through the existing Odoo working
transcript and/or user-facing provenance/citation rendering, then source/XML/log
providers. Do not add a second agent/runtime, retrieval registry, sidecar or vector DB
merely to satisfy the phase name.

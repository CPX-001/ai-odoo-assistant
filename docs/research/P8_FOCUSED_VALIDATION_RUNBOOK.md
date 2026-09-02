# P8 focused validation runbook

State: `EXECUTED / PASS`
Scope: P8 Evidence foundation, source/XML, configured logs, citations and real gates

This was intentionally an incremental gate. It did not authorize the full
repository, full addon, HOOT/browser or Product Behavior FULL regression unless a
focused failure demonstrated wider blast radius. No such expansion was necessary.

## Executed scope

The run pulled `origin/main`, compiled/linted all changed P8 Python files and ran:

```text
tests/unit/test_phase8_evidence_contracts.py
tests/unit/test_phase8_evidence_runtime.py
tests/unit/test_phase8_extension_evidence.py
tests/unit/test_phase8_supported_surface.py
tests/unit/test_phase8_product_profiles.py
tests/unit/test_phase8_source_log_evidence.py
tests/unit/test_capability_provider_extensions.py
tests/unit/test_phase7_feature_negotiation.py
tests/unit/test_phase7_live_extension_context.py
tests/unit/test_phase7_extension_composition.py
tests/addon/test_addon_boundaries.py
```

The Odoo-discoverable gate ran:

```text
addons/odoo_ai_assistant/tests/test_phase8_runtime_evidence.py
addons/odoo_ai_assistant/tests/test_canonical_plan_host_loop.py
tests/fixtures/odoo_addons/odoo_ai_assistant_p7_fixture/tests/test_phase7_fixture.py
```

The real Odoo/Codex gate runner is `tests/e2e/p8_real_evidence_gate.py`.

## Required properties proved

- deep immutable contracts and fail-closed provider/guard behavior;
- optional-provider isolation and reserved namespaces;
- effective Evidence IDs and Skill selectors;
- no automatic Evidence retrieval for generic/social turns;
- installed-addon source/XML diagnosis with logical locators and stale detection;
- correlated configured-log diagnosis with redaction;
- browser-safe host-owned citations and untrusted excerpts;
- hostile Evidence cannot override host policy;
- no retired unauthenticated callback, machine-auth or inventory-service path;
- installed-addon registry composition and canonical host-loop compatibility;
- effective Odoo user Environment remains `su=False`.

## Result

```text
static/compile/lint                 PASS
focused dependency-light           PASS — 61 tests
focused Odoo                        PASS — 20 tests, 0 failures/errors
P8-REAL-SOURCE-DIAGNOSIS           PASS
P8-REAL-LOG-DIAGNOSIS              PASS
P8-REAL-PROVENANCE                 PASS
P8-REAL-FRESHNESS                  PASS
P8-REAL-EVIDENCE-POLICY            PASS
P8-REAL-INJECTION-BOUNDARY         PASS
```

The authoritative commands, environment, repairs, reruns and explicitly unexecuted
suites are recorded in
`evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md`.

## Next implementation

P8 is accepted and P9 is eligible. Continue with one coherent source-lifecycle,
bounded-ingestion, lexical/FTS retrieval and chat-ingestion slice. Preserve the
existing Odoo authority, Evidence trust boundary and `CapabilityDefinition`
execution contract.

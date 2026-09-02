# P8 evidence core implementation checkpoint

Date: 2026-09-02  
State: `COMPLETE / ACCEPTED at e370af8acb7df175c0a90c8e17520c8576b4c6ce`

This checkpoint reconciles P8 against accepted P7 without adding a second agent,
action registry, persistence service or HTTP sidecar. The exact executed evidence is
`evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md`.

## Implemented contracts

- Deep immutable capability/context/Skill/provider JSON contracts that preserve
  normal `dict`/`list` compatibility.
- Versioned provider API, reserved namespaces, isolated optional-provider failures
  and fail-closed required-provider/guard behavior.
- Provider-neutral Evidence contracts, routing, catalog, bounded ledger, logical
  locators, access recheck, fingerprints, freshness and secret-safe projections.
- Public profiles normalized to exactly `user` and `technical`; profile selection
  never grants Odoo authority.
- In-process `assistant.runtime_inventory` with sanitized installed-module and
  registry facts; retired callback/machine-auth/inventory-service paths removed.
- Live bounded Evidence search/fetch through the existing extension decision engine
  and Codex trust partition.
- Installed-addon Evidence contribution through the existing
  `CapabilityProvider.evidence_providers` boundary and effective Skill selectors.

## Source/XML and log diagnosis

`assistant.source_evidence` searches only resolved roots of installed Odoo addons.
It accepts logical module-relative locators, blocks path escape and symlinks, enforces
file/time/byte limits, returns line citations and fingerprints, and reports changed
content as stale. Explicit module names constrain the scan to that module.

`assistant.log_evidence` reads only the configured Odoo logfile through a bounded
tail scan. It correlates the requested failure/turn metadata, expands tracebacks,
redacts secrets and credential-bearing URLs, exposes opaque byte locators rather
than filesystem paths, and detects inode/content freshness changes.

Both providers are Technical-profile resources. Their content is non-executable,
untrusted data and cannot change capabilities, policy, approval or ACLs.

## Provenance and citation projection

Selected Evidence references are projected into the normal browser result payload as
host-owned citation metadata. The citation contains provider, kind, title, logical
locator, fingerprint and freshness metadata; it does not copy raw untrusted excerpts
into the trusted partition.

The live wrapper keeps a bounded turn-scoped ledger. Its schema remains serializable,
but raw excerpt replay across reconnect is not claimed. Final citation metadata is
durable through the existing result payload, which is the P8 acceptance behavior.

## Supported-path cleanup

- Removed the obsolete sidecar-testing GitHub workflow.
- Removed the unauthenticated internal inventory callback.
- Removed the addon-local machine-auth primitive and residual inventory service.
- Kept historical `service/`, `installer/` and old evidence only as lineage material.
- Preserved the three reviewed host-owned `SELECT ... FOR UPDATE` concurrency locks;
  arbitrary or mutation SQL remains outside the model surface.

## Tests implemented and executed

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
addons/odoo_ai_assistant/tests/test_phase8_runtime_evidence.py
addons/odoo_ai_assistant/tests/test_canonical_plan_host_loop.py
tests/fixtures/odoo_addons/odoo_ai_assistant_p7_fixture/tests/test_phase7_fixture.py
tests/e2e/p8_real_evidence_gate.py
```

```text
focused dependency-light tests    PASS — 61
focused Odoo tests                 PASS — 20, 0 failures/errors
P8 real gates                      PASS — 6/6
effective Odoo Environment         PASS — su=False
P8 acceptance                      COMPLETE / ACCEPTED
```

The full repository/addon/HOOT/Product Behavior FULL suites were not required by the
focused runbook and remain unexecuted periodic debt.

## Explicitly deferred

- raw Evidence excerpt replay across reconnect and richer citation navigation;
- runtime/schema/security/navigation providers beyond current inventory/source/log;
- full host-owned observability spans/self-inspection capabilities;
- secret masked/copy/reveal UI;
- company Knowledge/RAG and uploaded-source lifecycle;
- domain-addon split and clean install/update/uninstall proof;
- repository acquisition and a separately reviewed Technical host broker.

## Next action

Proceed to the largest coherent P9 company Knowledge/RAG and source-lifecycle slice
identified by `EXECUTION_STATE.md`: bounded ingestion, lexical/FTS retrieval and chat
ingestion with their direct authority/security tests. A full regression remains
periodic unless a later runbook or concrete failure requires it.

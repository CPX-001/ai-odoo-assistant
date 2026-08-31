# Phase 7 implementation record — mini-framework and feature negotiation

Date: 2026-08-31  
Inspected starting `main`: `0b1bcab39b71dfbe02526cda7cf7ac8e218ac4b0`  
Phase: 7 — mini-framework, feature negotiation and Assistant self-awareness  
Current coherent slice: `P7.1-provider-extension-boundary-foundation`  
State: `FOUNDATION_FOCUSED_VALIDATED / LIVE_INTEGRATION_PAUSED_BY_PRODUCT_GATE`

## Why Phase 7 became eligible

Phase 6 was closed by the final current-product regression published at `0b1bcab`; the accepted
regression evidence is `docs/research/evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md`.

Phase 7 then began and the provider-extension foundation below was committed. After that start, the user approved a
new permanent product-behavior eval gate intended to exist before Phase-7 product expansion. Because this P7.1
foundation is deliberately isolated and has **not** yet changed the live effective capability catalog, do not roll it
back merely to make the chronology look cleaner. Instead:

```text
preserve isolated P7.1 foundation
 -> focused deterministic gate PASS at the published P7.1 foundation checkpoint
 -> pause before live effective-catalog wiring
 -> implement/execute Product Behavior Evals v1
 -> repair HARD product regressions
 -> resume P7.1 live integration only after that gate is green
```

Owning product gate documents:

```text
docs/research/PRODUCT_BEHAVIOR_EVALS_V1.md
docs/research/PRODUCT_BEHAVIOR_EVALS_CODEX_HANDOFF.md
```

## Slice objective

Establish the first P7.1 authority-safe extension boundary before any third-party provider is wired
into live turn execution:

```text
trusted installed addon declaration
 -> CapabilityProvider
 -> deterministic composition/conflict validation
 -> CapabilityRegistry
 -> existing CapabilityDefinition / executor / policy authority
```

This slice deliberately stopped before changing the effective product runtime catalog. Letting third-party
installed code alter the catalog is a security/authority-relevant boundary; the new composition contract must first
pass focused dependency-light tests. The newly inserted product-behavior gate now also blocks the subsequent live
wiring so that capability expansion cannot land before the current user-visible baseline is measurable.

## Implemented foundation

### CapabilityProvider contract

Added `runtime/capabilities/provider.py` with:

- stable dotted `provider_id` and monotonic integer version;
- static definitions or one deferred loader, never both;
- `CapabilityProvider.from_objects(...)` for explicit `@tool` handlers;
- optional vs required provider semantics;
- sanitized `CapabilityProviderStatus` for later diagnostics/manifest projection;
- an Odoo-native registry marker convention: `_odoo_ai_capability_provider` on a trusted installed
  model class;
- registry scanning only, not filesystem/package scanning across installed addons.

### Registry composition

`compose_capability_registry(...)` now:

- preserves the existing built-in cached package catalog;
- rejects duplicate provider identities;
- rejects capability/executor collisions rather than shadowing core authority;
- isolates optional provider loader/definition failures;
- preserves the valid core catalog when an all-optional extension set has an invalid dependency graph;
- records provider provenance per capability plus sanitized provider status;
- does not change `CapabilityDefinition`, executor, policy, ACL, approval or verification authority.

`discover_capabilities_for_env(env)` is prepared as the Odoo-registry-aware composition entry point. It is **not yet
wired into live turn execution** at this checkpoint.

## References used

The design follows the current repository playbook and `docs/CAPABILITY_FRAMEWORK.md`. The Project Atlas v1.1 is
the supporting design reference: Pydantic AI contributes the provider/bundle/atomic separation and stable discovery
semantics; FastMCP contributes the provider abstraction; Apexive shows Odoo-native discovery. None is introduced as
a runtime dependency. `CapabilityDefinition` remains the stricter host-owned executable unit.

The same Atlas and the Project Benchmark also identify agentic evals as a P0 gap: deterministic tests alone do not
prove correct tool selection, grounding, approval behavior, UX or cost/latency. `PRODUCT_BEHAVIOR_EVALS_V1.md`
turns that recommendation into the current promotion gate.

## Invariants

- Odoo remains operational and persistence authority.
- Business execution remains effective-user `su=False`.
- A provider can contribute definitions but cannot grant itself execution authority.
- Duplicate capability identity never silently overrides an existing definition.
- Optional provider failure cannot remove the core catalog.
- Raw extension exceptions do not become model/user-facing diagnostics.
- No arbitrary Python/package discovery, shell, SQL, sudo or unrestricted ORM is introduced.
- Provider metadata/configuration is data, not policy.
- Product-eval instrumentation must not capture raw private reasoning/secrets.

## Focused deterministic gate prepared

New dependency-light coverage:

```text
tests/unit/test_capability_provider_extensions.py
```

It covers:

- static provider composition and provenance;
- explicit decorated-handler contribution;
- duplicate provider identity rejection;
- optional loader failure isolation;
- required provider failure fail-closed behavior;
- capability collision rejection without core shadowing;
- invalid optional dependency fallback to the core catalog;
- deterministic Odoo registry marker discovery without inherited duplicate markers.

Required focused command before any further P7 code:

```bash
.venv/bin/python -m pytest -q tests/unit/test_capability_provider_extensions.py
```

Recommended static checks for the changed Python boundary:

```bash
.venv/bin/python -m py_compile \
  addons/odoo_ai_assistant/runtime/capabilities/provider.py \
  addons/odoo_ai_assistant/runtime/capabilities/registry.py \
  addons/odoo_ai_assistant/runtime/capabilities/__init__.py \
  tests/unit/test_capability_provider_extensions.py
.venv/bin/ruff check \
  addons/odoo_ai_assistant/runtime/capabilities/provider.py \
  addons/odoo_ai_assistant/runtime/capabilities/registry.py \
  addons/odoo_ai_assistant/runtime/capabilities/__init__.py \
  tests/unit/test_capability_provider_extensions.py
```

No repository-wide regression is authorized by this P7.1 foundation slice.

## Product gate before live P7 integration

After the focused P7.1 foundation test passes, **do not wire `discover_capabilities_for_env(self.env)` into live
turns yet**. Execute the handoff in `PRODUCT_BEHAVIOR_EVALS_CODEX_HANDOFF.md`.

The gate includes a permanent 54-case product behavior dataset, SMOKE/FULL runners, per-provider/tool timing,
permissions/persona coverage, real answer-streaming checks, and user-approved behavior such as one-shot Plan UX.

Two current-product issues are specifically called out for evidence-driven repair:

1. user-observed answer streaming may currently remain in `thinking` until the full answer arrives, despite the
   accepted historical P4 streaming contract;
2. current Plan is persisted as a user preference, while the approved product behavior is a removable one-shot
   composer tag consumed by the next submitted turn.

These are product contract changes/regression investigations, not reasons to weaken P7 authority invariants.

## Next action after product gate PASS

Resume **inside P7.1** and wire `discover_capabilities_for_env(self.env)` into every current Odoo-owned
effective-catalog composition surface (live host loop, plan/reversion path and settings/diagnostics). Then add an
installed test addon/provider fixture and focused Odoo coverage for enable/disable/uninstall/failure isolation before
attempting `P7-REAL-PROVIDER-DISCOVERY`.

Do not start P7.2 Skill/Bundle until the P7.1 effective runtime boundary has deterministic acceptance; that would
stack a second unvalidated contract layer.

## Phase-7 real gates still pending

```text
P7-REAL-PROVIDER-DISCOVERY
P7-REAL-SELF-AWARENESS
P7-REAL-DISABLEMENT
P7-REAL-CONTEXT-PROVIDER
P7-REAL-DISCLOSURE
P7-REAL-AUTHORITY
```

None has been executed or claimed by this checkpoint.

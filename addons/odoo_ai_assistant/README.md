# Odoo AI Assistant addon

The supported product is an Odoo 18 Community addon with an embedded, durable
agent runtime. The browser talks to Odoo; Codex App Server is a provider subprocess,
not a product daemon.

## Product model

The customer installs one Odoo AI Assistant product. Internal link/domain addons may
be introduced later to reduce domain coupling, but normal customers should not need
to understand or assemble that internal split.

There are exactly two public profile values for now:

```text
user
technical
```

Historical/internal `business`/`developer`-style values may remain for compatibility,
but they normalize to those two public profiles. A future Technical/host broker is an
execution boundary, not a third human role.

## Runtime flow

```text
OWL chat/context surface
 -> authenticated Odoo conversation + durable turn
 -> cron worker claims turn under effective user
 -> provider-neutral host decision loop
 -> effective Capabilities + Skills + JIT Context + Evidence providers
 -> relevant turns: bounded Evidence search/fetch -> untrusted working data
 -> Codex App Server adapter
 -> host validates calls/policy/effects
 -> execute with effective Environment and su=False
 -> verify, persist public activity and deliver final answer
```

Odoo owns identity, persistence, ACLs, record rules, companies, policy, approval,
execution and verification. The model proposes; it never grants itself authority.

## Capability framework

`runtime/capabilities/` contains the common extension contract:

- `CapabilityDefinition` — atomic executable schema/handler/risk/effect contract;
- `CapabilityProvider` — versioned installed-addon contribution boundary;
- `SkillDefinition` — trusted procedural guidance and selectors;
- `ContextProvider` — bounded just-in-time untrusted context;
- `EvidenceProvider` — bounded search/fetch with provenance/access/freshness;
- `EvidenceLedger` — bounded turn-scoped refs and selected excerpts.

Provider API mismatch, loader/collision/dependency/cycle failures and guard failures
are isolated/fail-closed at the host boundary according to provider optionality.
Deep JSON contracts use immutable `dict`/`list`-compatible wrappers.

The framework does not expose arbitrary SQL, Python, shell, sudo or unrestricted Odoo
method invocation.

## P8 Evidence checkpoint

The current checkpoint includes:

```text
EvidenceKind / Trust / Freshness
logical locators and stable refs
access check on collect and fetch
fingerprint/stale semantics
fine-grained per-provider failure isolation
question-sensitive source routing
bounded turn ledger
runtime/installation inventory provider
live provider-neutral search/fetch projection
secret-safe untrusted Evidence data
```

Installation inventory is in process and owned directly by
`assistant.runtime_inventory`. The obsolete GitHub Actions workflow, retired
`auth="none"` sidecar callback, addon-local machine-auth primitive and residual addon
inventory service have been removed from the supported tree.

Evidence never grants a capability or approval. Live mutable business facts remain
ORM queries; source/XML/log/docs/web providers are later P8/P9 slices. Durable ledger
restoration after reconnect and richer citation UI are also not claimed yet.

## Autonomy and writes

Effects follow:

```text
discover -> inspect -> prepare -> preview -> policy
 -> approval only when required -> execute -> verify
```

A full-control policy may execute permitted auto-executable effects without redundant
confirmation when the user has already expressed intent. It cannot bypass ACLs,
record rules, companies, field access or hard safety stops. Ambiguous writes are not
retried automatically.

## Source scope

Current source intelligence uses
`../../docs/CONTEXT_SOURCE_POLICY.md` and
`runtime/context_source_policy.json`. Historical `service/`, `installer/`, old
migrations/tasks/evidence and secret-bearing roots are excluded by default but remain
available for explicit lineage analysis where authorized.

## Controller/security boundary

All supported Assistant routes authenticate through Odoo. There is no supported
`auth="none"` Assistant route and no addon machine-secret HTTP inventory callback.
Controllers are transport adapters; they do not own policy or provider credentials.

## Validation state

P0-P7 are accepted. P8.0 plus the P8.1/P8.2 checkpoint is implemented with focused
tests prepared/updated, but those tests and P8 real gates remain pending. See:

```text
docs/research/EXECUTION_STATE.md
docs/research/P8_EVIDENCE_CORE_IMPLEMENTATION.md
docs/research/P8_FOCUSED_VALIDATION_RUNBOOK.md
tests/unit/test_phase8_evidence_contracts.py
tests/unit/test_phase8_evidence_runtime.py
tests/unit/test_phase8_extension_evidence.py
tests/unit/test_phase8_supported_surface.py
tests/unit/test_phase8_product_profiles.py
tests/unit/test_capability_provider_extensions.py
tests/unit/test_phase7_feature_negotiation.py
tests/unit/test_phase7_live_extension_context.py
tests/addon/test_phase8_runtime_evidence.py
tests/addon/test_addon_boundaries.py
addons/odoo_ai_assistant/tests/test_canonical_plan_host_loop.py
```

Do not interpret code or committed tests as PASS evidence.

## Extension rule

Before adding another tool/action/retrieval system, extend the current framework. A
trusted installed addon should contribute a versioned provider rather than edit the
core catalog. Skills and Evidence may improve reasoning, but every executable
operation still resolves to a host-validated `CapabilityDefinition` or a separately
reviewed future host-broker operation.

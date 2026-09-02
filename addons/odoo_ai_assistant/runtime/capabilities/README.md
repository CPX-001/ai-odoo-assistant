# Capability and Evidence framework

This package is the host-owned extension boundary of Odoo AI Assistant.

## Authority model

`CapabilityDefinition` remains the only atomic executable contract. A model may
propose a call, but the host still owns discovery, schema validation, effective
user identity, ACL/record rules, policy, approval, execution and verification.
Skills, context, manifests and Evidence never grant authority.

```text
CapabilityProvider
  -> CapabilityDefinition[]       executable, host validated
  -> SkillDefinition[]            trusted installed-code guidance
  -> ContextProvider[]            bounded JIT contextual data
  -> EvidenceProvider[]           bounded, cited, untrusted evidence
```

Business operations continue to use the effective Odoo `Environment` with
`su=False`. The framework does not expose arbitrary SQL, Python, shell, sudo or
unrestricted model methods.

## Capability providers

Installed trusted addons declare `CapabilityProvider` markers through the Odoo
registry. The provider API is versioned by
`CAPABILITY_PROVIDER_API_VERSION = "1"`.

Provider rules:

- IDs are stable and globally unique.
- Third parties use an addon-owned or reverse-domain namespace.
- `odoo.*`, `assistant.*` and `host.*` are reserved for core declarations carrying
  `metadata={"namespace_owner": "core"}`.
- Incompatible API versions fail closed with a sanitized code.
- Optional provider/resource failures are isolated; required providers fail closed.
- Schemas and metadata are normalized at construction rather than retained as
  mutable caller-owned dictionaries.

Adding Evidence to an existing provider does not add a second executable registry:

```python
CapabilityProvider(
    provider_id="vendor.sales_assistant",
    definitions=(...),
    skills=(...),
    context_providers=(...),
    evidence_providers=(...),
)
```

## Skills and JIT context

`SkillDefinition` supplies trusted procedural guidance and selectors. It cannot
create, reveal or authorize a capability that is absent from the effective
registry. `ContextProvider` contributions are projected as untrusted data and are
collected just in time for the current decision.

The lifecycle remains:

```text
discovered -> available -> revealed -> active
```

The eager default remains in force until product evals demonstrate that lazy
progressive disclosure preserves tool-selection quality.

## Evidence foundation (P8)

`evidence.py` defines a provider-neutral Evidence contract:

- `EvidenceKind`, `EvidenceTrust` and `EvidenceFreshness`;
- logical `EvidenceLocator` values rather than model-authored paths;
- `EvidenceRef` provenance, fingerprint, capture time, access scope and conflict
  grouping;
- bounded `EvidenceItem` excerpts/data;
- `EvidenceProvider` search/fetch and `EvidenceProviderCatalog` isolation;
- a question-sensitive `EvidenceRoutingPolicy` that prioritizes source classes
  without reintroducing rigid intent routing;
- `EvidenceLedger`, limited to 64 refs, 16 retained excerpts, 8 KiB per excerpt
  and 64 KiB total.

Access scope is checked while collecting a ref and again when fetching it.
Fingerprint changes are explicit as `stale`; they are not silently accepted.
Provider output is deeply copied/frozen, canonicalized and bounded. Common secret
shapes are redacted as a final safety layer, while collection code must still avoid
sensitive fields by design.

Evidence reaches the model only as structured data:

```json
{
  "source": "evidence",
  "trust_boundary": "untrusted_data",
  "reference": {"...": "host-owned metadata"},
  "excerpt": "bounded content",
  "data": {"...": "bounded content"}
}
```

It never enters the Skill/system instruction partition and cannot alter policy,
approval, capability availability or technical profile.

## Runtime inventory provider

`runtime_evidence.py` supplies the first built-in provider:
`assistant.runtime_inventory`. It derives a sanitized installation fingerprint and
bounded installed-module projection from the effective Odoo registry/ORM. It does
not expose credentials, absolute roots, commands or mutable business-record
snapshots. Technical metadata is bound to the Technical profile and Odoo group
checks.

## Current validation boundary

Dependency-light and Odoo-focused tests for the P8 foundation live in:

```text
tests/unit/test_phase8_evidence_contracts.py
tests/unit/test_phase8_supported_surface.py
tests/addon/test_phase8_runtime_evidence.py
```

The tests are part of the checkpoint, but a GitHub connector write does not count
as execution evidence. P8 real gates remain pending until run in the prescribed
Odoo/Codex environment and recorded under `docs/research/evidence/`.

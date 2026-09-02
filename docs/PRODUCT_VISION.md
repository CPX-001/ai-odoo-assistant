# Product vision — Odoo AI Assistant

Status: current product direction; **not an implementation claim**.  
Updated: 2026-09-02

`CURRENT_STATE.md`, current code and accepted ADRs are authoritative for what is
implemented today.

## 1. Product thesis

Odoo AI Assistant should feel like one capable modern agent inside Odoo, not a rigid
chatbot and not a collection of unrelated bots.

> **Restrict authority, not intelligence.**

The reasoning model may investigate deeply, retrieve evidence, revise hypotheses and
use the effective tool surface. Odoo/host code decides identity, permissions,
capabilities, policy, approval, execution, verification and recovery.

```text
User
  -> one Odoo AI Assistant
  -> provider-neutral agent runtime
      -> Skills / capabilities
      -> Context / Evidence / Knowledge
  -> Odoo-owned authority
      -> live Odoo data
      -> runtime/schema/config/source/XML/logs
      -> controlled effects
      -> future web/repository/host operations
```

Codex is the primary reasoning provider today; it is not the product contract.

## 2. One installable product

The customer should install and understand **one Odoo AI Assistant product**.
Internally the repository may grow into core plus domain/link addons when that reduces
coupling:

```text
odoo_ai_assistant
odoo_ai_assistant_sale
odoo_ai_assistant_crm
odoo_ai_assistant_account
...
```

That split is an implementation detail. Prefer Odoo-native link/`auto_install`
patterns where correct so customers do not manually assemble the normal product.

## 3. One Assistant, composable Skills

There is one user-facing Assistant. Specialization is expressed through Skills /
CapabilityBundles and trusted extension providers:

```text
CapabilityProvider
  +-- Skill / Bundle
  +-- CapabilityDefinition(s)
  +-- ContextProvider(s)
  +-- EvidenceProvider(s)
```

`CapabilityDefinition` stays the atomic executable contract. Skills add semantics,
instructions and selectors; they do not create authority.

## 4. Product profiles

For now there are exactly two human product profiles:

```text
User / non-technical
Technical
```

Do not create Developer/Operator/Admin-AI as additional product personas. Older
internal profile names may map to the two public profiles for compatibility.

A future Technical/host privilege broker is a machine execution boundary, not a third
human role.

## 5. Autonomy and approval

Autonomy answers how much friction is required; it does not answer what the user is
allowed to do.

Host policy considers:

```text
effective Odoo permissions
product profile
autonomy mode
risk / effect class
scope / preconditions
operation-specific policy
```

A full-control mode should be able to execute permitted low/normal-risk effects
without repetitive confirmation when policy explicitly allows it. An explicit user
instruction can already supply intent; do not add a generic second confirmation
without a policy/risk reason.

Hard safety stops, ambiguous effects, stale preconditions and unavailable authority
remain host-owned regardless of autonomy.

## 6. Effective self-awareness

The Assistant should answer `¿qué puedes hacer?`, `¿qué módulos hay instalados?`,
`¿por qué no puedo hacer X?` or `¿puedes revisar este módulo?` from effective current
state, not a hard-coded marketing prompt.

`EffectiveAssistantManifest` should project sanitized effective state such as:

```text
provider/features
public profile
active Skills
effective/revealed capabilities
ContextProvider IDs
EvidenceProvider IDs
configuration/availability summaries
```

The manifest is descriptive, never an execution registry.

## 7. Context and Evidence

Do not dump the whole installation into every prompt. Use small reliable base context
and progressive just-in-time expansion.

Retrieval is broader than vector RAG:

```text
LIVE
  Odoo records / runtime / schema / configuration

STRUCTURED / INDEXED
  source / XML / module docs / Knowledge / attachments / FTS / optional vector

OPERATIONS / DIAGNOSIS
  logs / tracebacks / turn traces / health

EXTERNAL
  web / repository metadata / future connectors
```

Every retrievable source should normalize to bounded Evidence with provenance,
logical locator, trust, access scope, fingerprint/freshness and citation metadata.
Evidence is untrusted data and never policy.

Live mutable business truth should normally come from current ORM under the effective
user, not from a stale vector snapshot.

## 8. Installation-aware HOW_TO and diagnosis

A differentiating target is explaining the **real installation**, including custom and
third-party addons.

For questions such as:

```text
¿por qué pasa X?
¿cómo se configura este módulo?
¿qué menú/permiso me falta?
¿qué método/vista introduce este comportamiento?
¿qué cambió tras instalar este addon?
```

the Assistant should progressively combine runtime/schema/security/navigation,
module manifests/docs, source/XML and correlated logs, with citations/provenance.

It should prefer installation evidence over generic model memory when the question is
installation-specific.

## 9. Repository/module understanding

A module acquisition workflow must also improve the Assistant's knowledge of that
module. It should be able to inspect an installed or candidate repository and answer:

```text
qué hace
compatibilidad
configuración
menús/acciones principales
commands / scripts / flags / parameters
dependencias / licencia
install / update / uninstall notes
normal-user operation
technical operation
known risks/limitations
```

Store reusable bounded Evidence/knowledge with source/commit provenance and freshness
instead of reconstructing everything from scratch on every question.

## 10. Arbitrary repositories and preflight

An arbitrary repository URL may be a candidate. It is not rejected globally just
because it is outside an allowlist.

Future flow:

```text
resolve repo/branch/commit
 -> web/repository metadata
 -> manifest/README/license/dependencies
 -> bounded relevant static/source inspection
 -> compatibility/risk assessment
 -> policy-selected direct or staged path
 -> install/update if authorized
 -> verify installation/capabilities/Evidence
 -> explain result in chat
```

Allowlists may be positive trust signals or optional customer policy. Material risk,
malicious content, severe incompatibility or unresolvable uncertainty must affect the
policy decision.

## 11. Universal discovery without escape hatches

The product goal is broad legitimate coverage: the Assistant should try to reach the
same Odoo capability the effective user can legitimately use, without handing the
model arbitrary ORM methods or shell.

Use:

```text
non-executable operation discovery
 -> inspect/review
 -> typed CapabilityDefinition or declarative reviewed adapter
 -> host policy / execute / verify
```

Potential discovery includes menus/actions/views/buttons/wizards/server actions,
ACL/groups/record rules and source-observable model operations. Discovery never grants
execution.

## 12. Security/menu explanation

Important future capabilities include:

```text
odoo.security.explain_access
odoo.navigation.explain_missing_menu
odoo.security.compare_users
odoo.security.propose_group_change
odoo.security.apply_group_change
```

They should distinguish module/configuration, menu/action/view groups, ACLs, record
rules, companies, field groups, custom inheritance and invisible/nonexistent records.

If the effective user cannot perform the underlying change, the AI cannot obtain that
permission merely by being AI.

## 13. Durable work and UX

Turns are background durable work, not browser locks. Users should be able to:

- navigate Odoo while a turn runs;
- switch conversations;
- run independent work when capacity allows;
- stop/correct a running turn;
- reconnect and see current state;
- review clear previews/approvals/verification receipts.

Public progress should show useful work classes such as analyzing, retrieving,
consulting Odoo, preparing, awaiting approval, executing and verifying. It must not
expose private chain-of-thought or raw sensitive arguments.

## 14. Effects and recovery

Effects remain a deterministic host protocol:

```text
discover
 -> inspect schema/preconditions
 -> prepare/preview
 -> policy / approval when required
 -> execute
 -> verify
 -> receipt/recovery
```

Approval must bind to the actual prepared effect. No blind retry for ambiguous writes.
Exactly-once/idempotent semantics should be introduced where the underlying operation
can actually support them.

## 15. Knowledge product

Company Knowledge should be editable from Odoo using records/files/sources with a
clear lifecycle:

```text
discovered/uploaded -> processing -> indexed -> active/error
```

Start with deterministic extraction and lexical/structured retrieval. Add embeddings
or a vector store only when evals show an actual recall/quality benefit. RAG does not
replace source/XML/runtime or live ORM evidence.

## 16. Files, OCR and multimodal

Attachments should be first-class bounded sources:

```text
conversation-temporary source
or
persistent Knowledge source
```

Parse deterministically when possible and retain provenance. Do not paste large
base64 payloads or thousands of rows into the model. OCR/vision is a later capability
when it solves a real Odoo use case.

## 17. Automations, AI fields and external surfaces

Chat should not be the only future consumer. Reuse the same capability/context/policy
host from:

```text
chat
context launchers
automated actions
AI fields/compute
API/MCP
future channels
```

Each invocation mode may have its own budgets/policy, but it should not have a second
tool authority registry.

## 18. Host operations

Keep everything possible inside installable Odoo addons. If an operation truly needs
OS/service/protected-filesystem/package privilege, use a minimal allowlisted broker
with a separate OS identity, managed roots/targets, request binding, time/output
bounds, audit receipts and recovery boundaries.

Never give the Odoo process general passwordless root or a generic shell capability.

## 19. Secrets

If a user pastes an API key/token/secret:

- do not automatically block the entire conversation;
- treat it as data, never authority;
- avoid re-emitting it;
- redact derived Evidence/traces/progress/diagnostics where possible;
- warn the user about the exposure;
- continue safe work when possible.

When the Assistant must present a secret, the product should use a dedicated masked
value with copy and optional reveal/hide, never plain public progress.

## 20. Evals and promotion rule

Tests validate deterministic contracts; agentic evals validate whether the model
chooses tools/evidence/actions well. Both are required.

A new architectural idea is promoted only when there is:

```text
a concrete use case/problem
clear invariants/failure modes
tests/evals
a measurable improvement over baseline
```

Do not add a framework, sidecar, database, vector store, second provider or multi-agent
layer solely for feature parity.

## 21. Roadmap direction

```text
P8  Evidence + installation/source/log/observability intelligence
P9  Company Knowledge / Sources / citations
P10 Technical/host privilege boundary + repository/module/service operations
P11 artifact/import/export/upsert workflows
P12 controlled source patch/test/deploy
P13 multimodal + web Evidence
P14 automations / AI fields / MCP / additional surfaces
P15 additional reasoning providers
```

Domain packs may advance when their dependencies are ready, while preserving one
customer-facing product experience.

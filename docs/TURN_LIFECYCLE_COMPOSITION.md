# Turn lifecycle and extension composition

Status: current runtime contract with P8 Evidence foundation.

## One host-owned turn

All product surfaces should converge on the same durable Odoo turn rather than
creating parallel agents or tool registries.

```text
Invocation surface
  -> authenticated Odoo conversation/turn
  -> effective user/company/context snapshot
  -> effective capability + extension catalogs
  -> provider-neutral host decision loop
  -> capability/evidence/effect operations
  -> durable public activity and final answer
```

Conversation stores history. Turn stores execution. Invocation context records the
launch surface and current record/view context but never replaces server-side
identity and permission reconstruction.

## Composition order

```text
1. discover installed CapabilityProviders
2. validate executable CapabilityDefinitions
3. compose Skills, ContextProviders and EvidenceProviders only from accepted owners
4. calculate available/revealed/active capabilities
5. calculate effective available Evidence IDs
6. activate Skills against effective capability/context/evidence catalogs
7. collect selected JIT context
8. route/fetch bounded Evidence when the current question needs it
9. project host guidance and untrusted data into separate provider partitions
10. validate every proposed capability/effect host-side
```

Failure of an optional extension is attributed to that provider and must not remove
healthy core/optional providers. Required extension failure closes the affected
catalog rather than silently degrading authority.

## Trust partitions

| Resource | Trust/use | Authority |
|---|---|---|
| `CapabilityDefinition` | host-validated executable contract | atomic execution unit |
| Skill instructions | trusted installed-code guidance | none by themselves |
| Assistant manifest | sanitized host projection | none |
| JIT context | untrusted contextual data | none |
| Evidence refs/contents | host metadata + untrusted contents | none |
| Provider private reasoning | never public/persisted | none |

Evidence and context must not be concatenated into the Skill/system instruction
partition. The Codex adapter receives only provider-neutral partitions produced by
the host.

## Read/retrieval path

```text
question
 -> choose effective provider/source classes
 -> search returns refs
 -> host checks scope/bounds/freshness
 -> fetch selected refs with scope recheck
 -> add refs/selected excerpts to bounded ledger
 -> model reasons over data
 -> answer cites provenance/freshness/conflicts
```

Current business facts use live ORM rather than stale inventory/document snapshots.
Installation claims favor runtime/schema/source/XML/configuration Evidence.

## Effect path

```text
discover -> inspect schema -> prepare EffectPlan
 -> preview -> policy/autonomy decision
 -> approval only when required
 -> execute under effective user
 -> verify -> receipt/recovery state
```

Full-control may remove redundant confirmations for policy-auto-executable effects,
but it never grants authority beyond the effective Odoo user. Ambiguous effects are
not retried automatically.

## Public progress

Public state is a sanitized projection such as analyzing, retrieving, consulting
Odoo, preparing a change, waiting for approval, executing and verifying. It does
not reveal chain-of-thought, raw tool arguments, credentials or source/log payloads.

## Persistence boundary

Odoo owns conversations, turns, task plans, public events, effect plans/receipts and
bounded Evidence ledgers. Provider processes remain ephemeral. Corpora, source
indexes and documents stay in their owning source/provider; a turn retains only the
bounded refs/excerpts needed for continuation and audit.

## Future surfaces

Chat, contextual launchers, AI fields, automations and an optional MCP adapter must
reuse the same capability, Evidence, identity and policy contracts. Surface-specific
budgets and invocation metadata are allowed; duplicated execution authority is not.

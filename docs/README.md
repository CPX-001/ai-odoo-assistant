# Documentation map

This file defines which repository documents describe the current product, target product and executable roadmap.

## Authority order

When documents disagree, use:

1. current code on `main` plus accepted ADRs;
2. current-state/architecture documents in the table below;
3. current tests;
4. executable research/playbooks for future work;
5. dated reports/archive material;
6. external references.

`PRODUCT_VISION.md` is authoritative for intended product direction but **never overrides current code/ADRs as an implementation claim**. Architecture changes that intentionally break an accepted invariant require a new/superseding ADR.

## Current documents

| Document | Status | Purpose |
| --- | --- | --- |
| `CURRENT_STATE.md` | current implementation | Audited snapshot of what exists now, including landed-but-unaccepted P3/P4 code and current limitations. |
| `PRODUCT_VISION.md` | current product direction | Defines the one-global-Agent target: broad Codex-level reasoning with Odoo/host authority, dynamic context/evidence/capabilities, non-blocking multi-chat, RAG and future technical operations. |
| `ARCHITECTURE.md` | current + target boundaries | Runtime, authority, persistence, concurrency and component boundaries. |
| `UNIFIED_AGENT_RUNTIME.md` | current | Turn lifecycle, provider/host split and recovery foundations. |
| `CAPABILITY_FRAMEWORK.md` | current contract + extension target | Atomic capability authority plus CapabilityProvider/Skill/Context/Evidence direction. |
| `CHAT_PRODUCT_FLOW.md` | current + next product invariants | Browser-to-Odoo durable turn/live-stream flow and non-blocking multi-chat target. |
| `KNOWLEDGE_INDEX.md` | target retrieval architecture | Evidence contract, installation intelligence, Knowledge/RAG and ingestion direction. |
| `FUTURE_MODEL_ROUTING.md` | deferred optional direction | Records late-stage local/multi-model routing without creating an active phase or implementation debt; preserves only lightweight compatibility rules now. |
| `QUERY_CONTRACT.md` | current | Schema-first live Odoo query/discovery contract. |
| `AGENT_RUNTIME_OPTIMIZATION.md` | current guidance | Runtime performance/quality guidance. |
| `DEPLOYMENT_CONFIG.md` | current | Supported embedded deployment/configuration. |
| `HOW_TO_WORKFLOW.md` | current status | HOW_TO behavior inside the unified agent; no separate router. |
| `codex/CODEX_AUTH.md` | current | Provider-owned Codex account lifecycle and DB activation gate. |
| `adr/README.md` + accepted ADRs | current decisions | Architecture decision log. |
| `HISTORICAL_DOCUMENTATION.md` | current index | Classification of archived/superseded material. |
| `DOCUMENTATION_AUDIT.md` | historical close-out baseline | 2026-08-26 documentation reconciliation record; later current docs supersede stale details. |

## Research and executable roadmap

`docs/research/` contains ordered implementation/evidence documents. They do not override implemented code/accepted ADRs.

Primary entry points:

- `research/README.md` — research/execution index;
- `research/EXECUTION_STATE.md` — **the current cursor** used by recurring roadmap execution;
- `research/CONTINUOUS_EXECUTION_PROTOCOL.md` — restartable slice/gate/validation rules;
- `research/REAL_ENV_VALIDATION_PROTOCOL.md` — named real product-path acceptance gates;
- `research/FOUNDATION_STABILIZATION_PLAYBOOK.md` — historical/current P0-P4 stabilization path; P0/P1 complete, P2 acceptance pending, P3/P4 implementation landed pending ordered gates;
- `research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md` — **P5+ gated product roadmap** derived from `PRODUCT_VISION.md`;
- `research/E2E_AGENT_LOOP_CONVERGENCE.md` — code-level reasoning loop convergence record that led to ADR-019;
- `research/PHASE23_REAL_VALIDATION_RUNBOOK.md` and `research/PHASE34_REAL_VALIDATION_RUNBOOK.md` — reproducible current P2-P4 validation procedures;
- `research/SLICE_TEMPLATE.md` — atomic implementation slice template.

## Formal roadmap chain

Current accepted/blocked state is summarized as:

```text
P0 baseline                                      COMPLETE
P1 provider boundary / host decision loop        COMPLETE
P2 structured failure presentation               HARD REAL GATES PENDING
P3 live public activity                          CODE LANDED; ACCEPTANCE BLOCKED BY P2
P4 real answer streaming                         CODE LANDED; ACCEPTANCE BLOCKED BY P2/P3

-- P2 -> P3 -> P4 acceptance required --

P5 natural non-blocking multi-chat + continuity
P6 deep planning / multi-step effects / EffectJournal
P7 mini-framework / self-awareness
P8 Evidence / source / logs / installation intelligence
P9 Knowledge / RAG
P10 Developer/Operator host operations
P11 imports/artifact workflows
P12 controlled source modification
P13 multimodal/web evidence
P14 additional surfaces/automation/MCP
P15 additional providers

Optional post-maturity idea (not a phase): local/multi-model routing; see `FUTURE_MODEL_ROUTING.md`.
```

Do not select a later phase merely because implementation ideas exist. Follow the blocking gates in `EXECUTION_STATE.md` and the evolution playbook.

The deferred model-routing note does not alter this chain, add gates or consume look-ahead budget. Unless a future measured use case justifies it, no router/model-profile subsystem should be implemented merely to preserve theoretical flexibility.

## No GitHub Actions for roadmap validation

The current roadmap must not use GitHub Actions for execution or acceptance while repository instructions say no usable runners/workers exist.

Required tests run in environments that actually have the repository/Odoo/Codex/browser/provider dependencies. Unrun tests remain validation debt and never become PASS by inference.

## Updating documentation

When runtime behavior changes:

1. update the relevant current document in the same coherent change;
2. update `CURRENT_STATE.md` if the implementation claim changes materially;
3. update `EXECUTION_STATE.md`/phase evidence if roadmap state changes;
4. add/supersede an ADR when deployment/authority/persistence/privilege/effect invariants change;
5. preserve historical reports rather than rewriting them to appear current.

## Retired lineage

`service/`, `installer/` and root historical migrations describe the former Assistant Service architecture. They are not current runtime instructions.

Useful algorithms/contracts from that lineage may be reimplemented inside the embedded architecture, but no sidecar path becomes current merely because historical code exists.

## External references

Odoo/OCA/Apexive/OpenAI/etc. are implementation/product references only. Borrow tested patterns when they reduce risk — for example OCA queue capacity/background imports, OCA reusable AI tools, Apexive Knowledge/provider breadth — but retain this repository's accepted authority/recovery semantics and validate dependencies before adopting them.

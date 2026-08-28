# Current implementation state

Revalidated on 28 August 2026 through P2.4 implementation checkpoint `1a643cd948b2a68c941863e6d6f411b968afd61f`.

## Baseline

- Odoo 18 Community; addon version `18.0.10.9.0`.
- Embedded Odoo runtime; browser talks only to Odoo.
- Durable Odoo turn/cron persistence; private working transcript and sanitized projections.
- Business capabilities execute under the originating effective user with `su=False`.
- ADR-019 host-owned iterative decision loop; `CapabilityDefinition` remains atomic authority.

## Phase 2

P2.1 schema, P2.2 provider normalization and P2.3 terminal persistence remain COMPLETE. P2.4 browser failure presentation is implemented but `REAL_ENV_VALIDATION_REQUIRED`.

The browser strictly validates `browser_status().failure`, preserves machine failure semantics and compatibility code, rejects malformed/sensitive/unbounded details, retains bounded stream error specificity instead of universal `service_unavailable`, renders deterministic category/effect guidance, and offers retry only for explicit `safe + none/not_started + retry`. `partial`, `unknown` and `recovery_required` never permit blind retry.

```text
P2-REAL-AUTH      REAL_ENV_VALIDATION_REQUIRED
P2-REAL-ACL       REAL_ENV_VALIDATION_REQUIRED
P2-REAL-TIMEOUT   REAL_ENV_VALIDATION_REQUIRED
P2-REAL-TOOLFAIL  REAL_ENV_VALIDATION_REQUIRED
P2-REAL-RECOVERY  REAL_ENV_VALIDATION_REQUIRED
```

Phase 2 therefore remains IN_PROGRESS.

## Phase 3

Production Phase 3 has not started because the P2 real gate is hard. Independent preparation exists: closed `PublicTurnEvent` Python/JS contracts, bounded kind/phase/status/resource/cursor semantics, explicit `agent.thinking` prohibition, trusted descriptor value prepared but not wired, and opt-in READ/ACTION/LIVE-VISIBILITY/REDACTION acceptance harness. LIVE-VISIBILITY uses a second DB connection and requires visibility before business-transaction commit.

No public-event production persistence, capability integration or activity UI is claimed. All four P3 real gates are `NOT RUN / BLOCKED_BY_PHASE2`.

## Validation in this environment

Dependency-light syntax/contract validation executed before publication: JS syntax checks, XML parse, Node contract runners (7 + 5 assertions), nine-gate manifest validation, 6 focused pytest tests and Python compilation. Odoo install/update, Odoo suites, HOOT and all P2/P3 real gates were NOT RUN here.

## Safety/architecture

Odoo remains authority. No generic arbitrary SQL, Python, shell, sudo, unrestricted ORM method surface, sidecar or parallel tool registry has been added. Provider/private reasoning/raw tool payloads are not public presentation data.

## Phase 4

`NOT_READY`. It requires formal Phase 2 and Phase 3 completion with mandatory real-environment evidence.

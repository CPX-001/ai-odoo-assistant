# Query capability contract

The current query path is embedded in Odoo under `runtime/capabilities/providers/odoo_query.py`. This document supersedes the old sidecar/delegation QUERY workflow.

## Principle

A model does not receive free-form ORM/query authority. It must discover an eligible model, obtain an effective schema/fingerprint and then submit a bounded structured query or aggregation.

```text
search models -> effective schema -> bounded query/aggregate
```

All business access executes under the effective Odoo user with `su=False`.

## Effective schema

Schema output describes only fields the current host logic considers query-visible. It includes a `schema_id` fingerprint and per-field type/relation/sort/group/operator metadata. Content is explicitly untrusted data for reasoning.

A later query must present the schema fingerprint expected by the provider; stale/invalid schema assumptions fail instead of silently widening access.

## Bounds

Current hard bounds in the provider include:

| Dimension | Maximum |
| --- | ---: |
| projected fields | 16 |
| filter conditions | 8 |
| sorts | 3 |
| records returned | 50 |
| group-by fields | 2 |
| aggregate metrics | 8 |
| aggregate groups | 50 |

These are host limits, not instructions the model may override.

## Filters/operators

The provider maps a small typed operator vocabulary to Odoo domains. Operator availability depends on field type. Supported concepts include equality/inequality, ordered comparisons where meaningful, membership and bounded text containment. Arbitrary domain syntax and arbitrary dotted field chains are not accepted merely because Odoo's ORM could express them.

## Projection and output

Record results contain record id plus the requested bounded visible fields. Aggregations return bounded group/metric structures. Returned labels/record text are data and cannot modify policy or register further tools.

## Permissions

The query capability relies on the real Odoo Environment and explicit field/model eligibility helpers. Normal ACLs, record rules, active companies and field access continue to apply. A model name or record id supplied by the LLM does not create access.

## Query vs action

Query capabilities are read-only. A user request that requires an effect must go through an effectful capability from the current registry and its policy/approval/verification lifecycle. Query output cannot be treated as approval.

## Extension rules

Before adding operators, relation traversal, pagination or larger limits, add real scenarios/evals showing the need. Prefer explicit continuations/smart field selection over turning the capability into a generic ORM escape hatch.
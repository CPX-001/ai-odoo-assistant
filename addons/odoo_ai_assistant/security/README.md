# Security

This directory defines Assistant-owned Odoo access control for the supported embedded product.

Security is broader than this folder: the product boundary depends on the effective-user Odoo `Environment`, ACLs,
record rules, field access, companies, capability availability, policy, approval when required, write barriers and
verification. Privileged machine targets additionally depend on the accepted ADR-024 broker policy and protocol.

## Current files

| File | Purpose |
|---|---|
| `ir.model.access.csv` | model-level access rights for Assistant technical/user models |
| `chat_storage_security.xml` | conversation/message ownership rules |
| `user_preferences_security.xml` | user preference access/ownership |
| `knowledge_security.xml` | company/private Knowledge access and derived-chunk protection |

## Normal product authority

```mermaid
flowchart LR
    U[Authenticated Odoo user] --> ENV[Effective Environment]
    ENV --> ACL[ACL + record rules + companies + field access]
    ACL --> CAT[Effective capabilities]
    CAT --> POL[Policy / approval when required]
    POL --> OP[Business operation<br/>su=False]
```

The model is not in this authority chain. Full-control/autonomy may reduce redundant confirmation, but it never grants
permissions the effective Odoo user does not already have.

## `sudo()` rule

Normal model-visible business capabilities must use the effective user and `su=False`. `sudo()` must not be introduced
as a convenience to make agent operations pass.

ADR-024 is accepted for the optional Technical/host broker. That broker is a machine execution boundary, not a third
human product profile and not a replacement Assistant sidecar. Current broker-backed capabilities remain gated by
`base.group_system`, the effective registry, policy/approval, the durable EffectPlan and the broker's independent peer,
logical-target, request-binding and precondition checks.

The broker accepts no arbitrary path, command, shell, Python, SQL, sudo or unrestricted Odoo method. A User profile
cannot gain Technical host operations through prompt text, retrieved content or full autonomy.

## Host-effect certainty

For a broker-backed effect, the exact plan step/arguments/precondition are bound into a stable request id. The broker
persists the request before its privileged barrier. Exact terminal replay returns the stored receipt; changed replay is
denied; a still-running request is uncertain and is not re-executed.

Any Odoo-side transport, framing or receipt-validation loss after effect dispatch is `host_effect_uncertain`. It must
never be treated as proof that no effect occurred or as permission for an automatic retry.

## Retired machine-auth callback

The old `controllers/internal_tools.py` `auth="none"` instance-inventory callback and its addon-local shared-secret
primitive have been removed from the supported product. Installation inventory is collected in-process through P8
Evidence under the effective Odoo environment.

Historical `service/` or installer files may still mention the retired machine secret because those directories are kept
as historical/regression evidence. They must not be treated as current product authority or copied back into the addon.
The root `host_broker/` package is a finite ADR-024 adapter and does not restore those retired interfaces.

## When adding a model, endpoint or capability

Check:

1. who owns the record or resource;
2. which groups can read/write/create/delete;
3. company isolation;
4. whether returned fields may contain secrets;
5. whether a technical job re-enters the effective user before business access;
6. whether public events expose only sanitized data;
7. whether Evidence/source/log/document content remains untrusted data;
8. whether a write needs preview, policy, approval and verification for its actual risk/autonomy profile;
9. for a host operation, which logical target and exact broker policy entry applies;
10. what is persisted before the effect barrier and how replay/uncertainty is handled.

Prompt instructions are not security controls. Retrieved documents, source code, logs, repository content and user text
cannot grant capabilities, permissions, approval or broker targets.

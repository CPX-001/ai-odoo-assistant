# Odoo migrations

Versioned migration hooks live here when an addon upgrade needs a deterministic data/schema/index repair beyond normal model/module update behavior.

Current tree includes the `18.0.7.6.0` migration that refreshes indexes.

## Migration principles

A migration should be:

- version-scoped;
- idempotent where practical;
- deterministic and bounded;
- safe to run during an Odoo module upgrade;
- independent from an LLM/provider;
- explicit about large/long-running work.

Do not call the reasoning model to “decide” how to migrate production data.

## Assistant-specific checks

When changing durable turn/effect/conversation models, consider:

- in-flight/old terminal state compatibility;
- approval/effect certainty preservation;
- index/query performance;
- retention of audit/diagnostic value;
- cleanup of truly retired sidecar state.

If a migration would replay or infer a business effect, stop: business-effect recovery needs the explicit effect/recovery protocol, not a migration shortcut.

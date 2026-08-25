# Unified agent runtime optimization pass

This note records the contained hot-path/retrieval optimization pass requested after ADR-014.
It does not redefine the Source of Truth and does not reopen batch/recovery.

## What changed

- `RuntimeAgentFactory` keeps one SQLAlchemy Engine/sessionmaker and reuses that infrastructure for
  chat history, instance-summary reads, plan stores, and agent retrieval. A fresh `Session` still
  scopes each DB operation/transaction.
- The unified agent advertises the existing knowledge and structural-source tools alongside Odoo
  tools. They are lazy: registering them performs no knowledge query, source inventory request, or
  filesystem scan.
- `odoo.get_instance_facts` exposes sanitized checked Odoo version/installed-module facts only when
  the reasoning turn needs them; database identity and physical addons roots are not returned.
- `source.inspect_module` gives Codex a bounded structural entry point into one exact installed
  custom/OCA/third-party addon when the relevant method/model/field is not known yet. Actual source
  claims still require `source.read_excerpt` and fingerprint revalidation.
- Source retrieval resolves inventory/roots only on the first instance/source call that needs them
  and then queries the persistent source index. Normal turns never invoke the source scanner.
- Knowledge uses the existing PostgreSQL FTS store and preserves `KnowledgeRef` fingerprint
  revalidation before an excerpt becomes checked Evidence.
- Source keeps structural lookup (`find_symbol`, model extensions) before a bounded
  fingerprint-checked excerpt.
- Recent conversation context now spends its deterministic character budget from newest to oldest,
  then presents the retained slice chronologically.

## Retrieval policy

The agent chooses the narrowest source lazily:

| Request shape | Expected retrieval |
| --- | --- |
| General version-independent concept | concise model answer; no decorative retrieval |
| Live counts/records | Odoo query/aggregate only |
| Record mutation | Odoo effective schema + preview only |
| Version/module-dependent capability | `odoo.get_instance_facts` first |
| Internal implementation/behavior | source structural lookup -> checked excerpt |
| Named custom/OCA/third-party addon | instance facts -> `source.inspect_module` if needed -> checked excerpt |
| Configuration/how-to | version/modules when relevant -> checked knowledge/source; Odoo schema/navigation only when useful |

Search candidates and module-inspection results remain untrusted pointers. The pass deliberately
keeps discovery and `read_excerpt` separate. Current lexical search does not expose a sufficiently
strong deterministic promotion signal to auto-select top-1 without risking irrelevant evidence.
Fingerprint revalidation is never skipped.

Configuration answers must not invent an exact Settings location. `res.config.settings` is a
transient wizard and remains outside generic business-record discovery; when implementation evidence
is required, the agent can inspect the relevant module/model extensions statically instead of
querying wizard records as business data.

## PostgreSQL FTS

The current knowledge schema already has a GIN index on `knowledge_chunk.search_vector`. No
pgvector, embeddings, external retrieval service, or new dependency was added. Title/body weighting
and alternative tsquery strategies should only be changed after running `EXPLAIN (ANALYZE)` and a
representative Spanish/English Odoo retrieval set against the deployed Assistant PostgreSQL.

## Lightweight latency baseline

Sanitized timing logs now expose only phase/tool names and durations; no prompts, payloads, record
values, filesystem paths, or credentials are logged.

Odoo-side phases:

- `odoo_prepare` for server-side screen/message context + policy/payload preparation;
- `odoo_assistant_http` for the local Odoo -> Assistant round-trip.

Assistant Service phases:

- `history_load`
- `instance_context`
- `codex_app_server_startup_initialize`
- `codex_thread_start`
- `codex_turn_start`
- `codex_reasoning_and_tools`
- `tool_call` with the logical tool name
- `agent_plan_persist`
- `agent_write_execution`
- `codex_total`
- `assistant_turn_total`

The connector environment used for this implementation has no deployed Odoo/PostgreSQL/Codex
runtime, so it would be misleading to commit synthetic millisecond figures. The structural baseline
is still deterministic:

| Cost | Before | After |
| --- | ---: | ---: |
| New Assistant SQLAlchemy Engine for history | 1 per turn with history | 0 |
| New Assistant SQLAlchemy Engine for instance summary | 1 per turn | 0 |
| New Assistant SQLAlchemy Engine for unified knowledge/source | unavailable in unified agent | 0; shared pool |
| Version/module inventory | not available to unified reasoning | lazy checked metadata tool |
| Source inventory/root preparation | not available in unified agent | only when retrieval needs source runtime |
| Source filesystem scan in normal turn | 0 | 0 |
| Codex App Server process/initialize | 1 per turn | 1 per turn, now measured |
| Conversation char budget | older retained slice could evict newer context | newest retained slice |

For a deployed before/after table, run a few representative turns only: pure Odoo aggregate,
instance-aware configuration/how-to, structural custom-source explanation, a follow-up with history,
and an unavailable retrieval/provider case. Use the timing log lines rather than hundreds of
prompts.

## App Server persistence decision

This pass does **not** pool Codex App Server processes. The current adapter owns one event queue,
request synchronization, and lifecycle per client. Safe reuse therefore needs a dedicated design:

1. one bounded persistent App Server process per compatible runtime/model domain;
2. ephemeral threads per Assistant turn;
3. an event router keyed by thread/turn/request identity;
4. bounded concurrency/backpressure;
5. strict separation of dynamic tool executors and events between users/turns;
6. idle timeout, health detection, restart, and cleanup;
7. no weakening of the existing thread policy/workspace isolation.

Implement this only if `codex_app_server_startup_initialize` is a material fraction of real turn
latency. Otherwise streaming gives more perceived-latency benefit with less runtime risk.

## Streaming boundary

Nothing in this pass requires a browser-to-Assistant connection. A future path can remain:

`Codex App Server events -> provider-neutral AgentTurnEvent -> Assistant endpoint -> Odoo -> Owl`.

No SSE, WebSocket, Odoo bus, or HTTP chunking is introduced here.

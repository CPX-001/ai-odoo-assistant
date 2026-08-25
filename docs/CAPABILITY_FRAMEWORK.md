# Addon-local Capability Framework

## Goal

`odoo_ai_assistant` behaves as a small capability host inside the addon. New tools are
declared once and discovered automatically. The agent runtime, planner, policy layer and
future transports consume the same catalog instead of maintaining parallel lists.

The framework is intentionally transport-neutral. Its wire descriptor is MCP-shaped
(JSON Schema input/output plus metadata), but it does not start an MCP daemon or another
HTTP service. A future MCP/OpenAPI adapter can expose the same catalog without changing
provider code.

## Layout

```text
odoo_ai_assistant/
  runtime/
    capabilities/
      contracts.py
      decorators.py
      registry.py
      executor.py
      validation.py
      providers/
        odoo_runtime.py
        <new capability files>.py
```

`providers/**` is recursively discovered with `pkgutil.walk_packages`. A provider does
not need to be imported from `providers/__init__.py` and does not need an Odoo model,
XML record, registry edit, or relation.

## Adding a tool

Create one Python file under `runtime/capabilities/providers/`:

```python
from ..contracts import CapabilityEffect, CapabilityRisk
from ..decorators import tool


@tool(
    name="odoo.partner_lookup",
    description="Find visible partners by name.",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 1}},
        "required": ["query"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {"records": {"type": "array"}},
        "required": ["records"],
        "additionalProperties": False,
    },
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
)
def partner_lookup(context, arguments):
    records = context.env["res.partner"].search(
        [("name", "ilike", arguments["query"])],
        limit=10,
    )
    return {
        "records": [
            {"id": record.id, "name": record.display_name}
            for record in records
        ]
    }
```

That file is sufficient for discovery. The composition root later asks
`discover_capabilities()` for the effective turn catalog.

## Definition contract

Each capability is the single source of truth for:

- stable tool name and version/executor id;
- human description;
- JSON Schema input and output;
- risk and effect class;
- approval requirement;
- optional Odoo groups and dynamic guard;
- default enablement;
- per-tool call/input/output budgets;
- handler function;
- source module/qualname for diagnostics.

Actions are not a second extension mechanism. A mutating action is a capability with a
write/action risk, effect metadata and approval policy. Reads, retrieval, diagnostics,
host utilities and future low-level integrations use the same protocol.

## Per-turn execution

`CapabilityContext` carries the effective Odoo `Environment`, turn/conversation ids,
screen data, bounded metadata and an event sink.

The environment is deliberately the originating user's environment. Normal Odoo
capabilities therefore inherit ACLs and record rules naturally. The framework itself
does not add `sudo()` or silently switch identity.

A capability implementation can technically use lower-level facilities already
reachable from that environment, including `env.cr`. That is an explicit provider
decision, not a hidden framework feature. The core addon does not ship a generic SQL
tool. Introducing one later must be an explicit policy/security decision, but it would
not require a new orchestration architecture.

Handlers can be synchronous or async. They execute in-process; synchronous Odoo code is
not moved to a thread. Inputs and outputs are validated against the declared bounded
schema before crossing the model boundary.

## Discovery and safety

Discovery is deterministic and cached per Odoo worker:

1. recursively import provider modules;
2. inspect decorated functions defined by each module;
3. reject duplicate names/executor ids;
4. build one `CapabilityRegistry`;
5. filter availability against the effective turn context;
6. advertise only the resulting definitions.

Discovery grants no authority by itself. Risk/effect/approval metadata remains
host-declared, and the eventual composition root decides which discovered capabilities
are exposed for each turn.

## Transport adapters

The current descriptor is deliberately close to MCP:

```json
{
  "name": "odoo.runtime_identity",
  "description": "...",
  "inputSchema": {"type": "object"},
  "outputSchema": {"type": "object"},
  "meta": {
    "executor_id": "odoo.runtime_identity.v1",
    "risk": "metadata",
    "effect": "read-only",
    "approval_required": false,
    "tags": ["odoo", "runtime", "identity"]
  }
}
```

The embedded Codex adapter will compile these definitions into the existing reasoning
engine's tool contracts. A future actual MCP or OpenAPI adapter should translate this
same registry rather than introduce another tool registry.

## Migration rule

Legacy hard-coded tool lists such as `agent_tool_specs()`,
`agent_tool_policy_specs()` and hand-composed query/action/retrieval registries are
migration inputs, not the desired final architecture. As each old tool moves into the
addon, its schema, policy metadata and handler binding should converge into one
`@tool(...)` definition.

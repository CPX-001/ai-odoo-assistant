# Historical M2 task-packet index

> Archive notice: this directory records the former M2 UI/context/delegation milestone. It is historical implementation evidence, not the current browser/runtime contract.

M2 introduced early Odoo UI/context flows and service-era delegation machinery. The current product still preserves the important authority principles—browser context is untrusted, Odoo derives identity, and ORM access runs under the effective user—but the operational path is now Odoo-native and no longer depends on a separate Assistant Service.

Keep the packets for chronology, security reasoning and regression reference. Do not revive their sidecar endpoints, machine-auth/delegation transport or milestone sequencing as current requirements.

Current replacements:

- chat/browser flow: `../../../CHAT_PRODUCT_FLOW.md`;
- runtime/authority: `../../../ARCHITECTURE.md`, `../../../UNIFIED_AGENT_RUNTIME.md`;
- implementation snapshot: `../../../CURRENT_STATE.md`.

The parent archive policy is `../README.md`.

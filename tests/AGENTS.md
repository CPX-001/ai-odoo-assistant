# Test rules

## Git

Work directly on `main` unless the user explicitly asks for a branch or pull request.

## Current product priority

For the embedded addon/runtime, prioritize:

- unit and contract tests for capabilities/policy;
- Odoo 18 integration tests;
- queue/restart/cancellation/recovery tests;
- effective-user ACL, record-rule, field-access and multi-company tests;
- preview/approval/verification and idempotency/recovery tests for effects;
- Codex isolation/account-gate tests;
- prompt-injection and untrusted-data boundary tests;
- OWL/UI tests for account gating, progress and approval surfaces;
- agentic evals when acceptance depends on model tool/source/action selection.

Do not treat a passing deterministic suite as proof of agent quality.

## Legacy tests

Tests under sidecar-era `service/`, `installer/`, old deployment fixtures and milestone E2E scripts are historical/regression evidence. Run or modify them only when the task touches that preserved lineage or a port intentionally reuses one of its contracts. They are not acceptance gates for current embedded architecture by default.

## Deployment variability

When testing filesystem/runtime deployment behavior, include non-default Odoo `data_dir`/executable locations where relevant. Avoid assumptions about fixed service names, ports or a separate Assistant DB because those are not current product invariants.
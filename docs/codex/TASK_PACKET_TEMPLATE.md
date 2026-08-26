# Task packet template

Use this template only when a bounded implementation task benefits from a hand-off packet. Current code/ADRs remain the source of truth.

## 1. Task

- **Title:**
- **Repository:** `CPX-001/ai-odoo-assistant`
- **Inspected main SHA:**
- **Owner/agent:**
- **Status:** planned | active | blocked | done

## 2. Problem and acceptance

Describe the concrete problem and the observable behavior that must exist when complete. Separate required behavior from optional ideas.

## 3. Current baseline

List relevant current paths/classes/models/tests and what they do now. Note documentation/code contradictions before implementation.

## 4. Invariants

Select/apply relevant constraints:

- Odoo is host/persistence/identity authority.
- business operations use effective user `su=False`;
- model output cannot grant capability/permission;
- reuse current Capability Framework and turn queue;
- no arbitrary SQL/Python/shell/sudo/unrestricted methods;
- effectful work keeps preview/policy/approval/verification semantics;
- retrieved/user-controlled text is untrusted data;
- Codex credentials remain provider-owned under Odoo `data_dir`.

Add task-specific failure modes/budgets.

## 5. References

- Current ADR/docs:
- Relevant project research snapshot:
- External reference(s), if useful:
- Pattern to adopt:
- Pattern/dependency explicitly rejected:

Do not require an external framework merely because it appears in a benchmark.

## 6. Implementation scope

- Files/components expected to change:
- Existing infrastructure to reuse:
- Data/schema/config changes:
- Compatibility/migration concerns:

## 7. Verification

- Deterministic unit/contract tests:
- Odoo integration/install/update/restart checks:
- ACL/record-rule/company cases:
- write/approval/recovery cases if applicable:
- agentic eval(s) if model behavior matters:
- security/prompt-injection cases if retrieval/untrusted content is involved:

## 8. Documentation/cleanup

List current docs/ADRs/readmes that require updates and any obsolete current-path code/docs to remove or mark historical.

## 9. Completion evidence

Record commit(s), commands/checks run, results, known limitations and any follow-up that is genuinely outside scope. Do not present partial work as complete.
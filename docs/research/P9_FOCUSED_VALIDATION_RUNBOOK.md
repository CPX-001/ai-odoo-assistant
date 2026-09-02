# P9 focused validation runbook

State: `PREPARED / NOT EXECUTED`
Scope: first P9 company Knowledge lifecycle, FTS Evidence and chat ingestion slice

This is the blocking validation for the implementation recorded in
`P9_KNOWLEDGE_FIRST_SLICE.md`. It does not authorize P10 and no result in this file is
PASS until the command is actually executed and recorded as evidence.

## 1. Static/dependency-light scope

Compile/lint the P9-changed Python/JS/XML surfaces using the repository's current
validation commands, then run at least:

```text
tests/unit/test_phase9_knowledge_routing.py
tests/unit/test_phase8_evidence_contracts.py
tests/unit/test_phase8_evidence_runtime.py
tests/unit/test_phase8_extension_evidence.py
tests/unit/test_phase8_source_log_evidence.py
tests/unit/test_phase7_live_extension_context.py
tests/unit/test_capability_provider_extensions.py
tests/addon/test_addon_boundaries.py
```

The inherited P8/P7 cases are intentional regression coverage for Evidence trust,
provider isolation, routing and addon boundaries changed by the new provider.

## 2. Focused Odoo scope

On a disposable Odoo 18 Community database with the addon updated to current main,
run:

```text
addons/odoo_ai_assistant/tests/test_phase9_knowledge.py
addons/odoo_ai_assistant/tests/test_phase9_knowledge_capability.py
addons/odoo_ai_assistant/tests/test_phase8_runtime_evidence.py
addons/odoo_ai_assistant/tests/test_canonical_plan_host_loop.py
```

Required focused properties:

- source lifecycle reaches `active` after deterministic processing;
- FTS search returns the exact expected source/chunk;
- Evidence citations carry source/version/chunk provenance;
- source mutation makes old refs stale before and after reindex;
- company sources are visible only through effective company access;
- private sources remain owner-only;
- ordinary users cannot create/modify derived chunks directly;
- source owner/company lifecycle fields cannot be forged;
- temporary attachment markers are stripped from persisted user messages;
- attachment binding is owner-only and `client_request_id` retry-safe;
- `assistant.knowledge.ingest_attachment` is discovered through the existing
  capability framework;
- its preview binds the current attachment fingerprint, its handler is idempotent and
  its verification resolves the created source;
- the ingestion call budget matches the eight-attachment turn bound;
- effective Odoo business/runtime context remains `su=False`.

## 3. Browser/asset smoke

Because this slice changes the Assistant composer, perform a focused browser smoke
before acceptance even if the full HOOT regression is deferred:

1. open the Assistant panel;
2. attach a supported small text file;
3. verify the chip/name is shown and can be removed;
4. reattach and submit an explicit "add this to Knowledge" request;
5. verify the visible user message contains no internal marker;
6. verify normal send/stop/redirect behavior still works without an attachment;
7. verify unsupported/oversized uploads show a bounded error and do not start a turn.

If a deterministic HOOT test is added during repair, include it in the focused gate.

## 4. Real Odoo/Codex gates

Runner:

```text
tests/e2e/p9_real_knowledge_gate.py
```

It must be executed through `odoo-bin shell` against a disposable `odoo_ai_*`
database while a separate Odoo worker process serves cron/turn processing. Set the
real Codex executable through `P9_CODEX_EXECUTABLE`.

The runner covers:

```text
P9-REAL-UPLOAD-INGEST
P9-REAL-CHAT-INGEST
P9-REAL-FTS
P9-REAL-CITATIONS
P9-REAL-ACL
P9-REAL-REINDEX
P9-REAL-LARGE-DOCUMENT
```

`P9-REAL-SEMANTIC-GAIN` is not applicable while P9 intentionally has no vector
backend. It becomes a real gate only if a later P9 slice introduces embeddings after
measured lexical-retrieval gaps.

## 5. Failure policy

Repair the smallest authoritative layer responsible for a focused failure and rerun
the failed gate plus the affected neighbors. Do not weaken:

- Odoo record rules/ACLs;
- Evidence `USER_CONTENT` trust;
- stale fingerprint/version checks;
- capability authority/preview/verification;
- turn idempotency;
- file/chunk/result bounds.

Do not solve a retrieval miss by introducing embeddings before proving the lexical
baseline is insufficient.

## 6. Acceptance record

When all blocking focused and real gates pass, create an immutable evidence file under
`docs/research/evidence/phase9/<date>/` containing:

- exact tested main SHA;
- environment/version information;
- exact commands;
- test counts;
- repairs and reruns;
- all seven P9 real gate results;
- explicitly unexecuted broad regressions;
- final P9 acceptance decision.

Until that record exists, `EXECUTION_STATE.md` must remain
`IMPLEMENTED_AWAITING_FOCUSED_VALIDATION` or a more specific failing state.

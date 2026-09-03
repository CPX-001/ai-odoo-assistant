# P12 focused validation runbook

State: `P12.1 READY / PARTIAL DEPENDENCY-LIGHT CHECK ONLY`  
Scope: bounded source roots/workspace identity/fingerprint authority; no source editing
or deployment yet.

Implementation authority:

```text
docs/adr/ADR-025-controlled-source-workspaces.md
docs/research/P12_SOURCE_WORKSPACE_FOUNDATION.md
```

## 1. Focused dependency-light gate

On the exact current `main` execute:

```text
python -m compileall -q \
  addons/odoo_ai_assistant/runtime/source_workspace.py \
  tests/unit/test_phase12_source_workspace.py \
  addons/odoo_ai_assistant/tests/test_phase12_source_workspace.py

python -m unittest -v tests.unit.test_phase12_source_workspace
```

If the repository's normal lint tool is available, run it on those files plus the
changed import/manifest files. Absence of the lint executable is not PASS.

Required properties:

- host-generated workspace ids;
- deterministic source baseline fingerprints independent of timestamps/physical paths;
- source and workspace fingerprints diverge independently;
- no source write during prepare/inspect/delete;
- absolute/traversal/malformed workspace identity rejected;
- source-root/workspace overlap rejected;
- source symlink rejected rather than followed;
- file/count/byte bounds enforced before publish;
- obvious secret source files are not copied;
- secret-named workspace tampering fails closed;
- delete cannot escape the managed workspace root;
- different binding cannot inspect/delete another workspace.

The author-side preparation run executed 10 dependency-light tests successfully, but
rerun them on the committed SHA before recording formal focused evidence.

## 2. Focused Odoo gate — HARD before P12.2

Update the addon on a disposable Odoo 18 Community database and run exactly:

```text
/odoo_ai_assistant:TestPhase12SourceWorkspace
```

Expected selector: **3 methods**.

Pass requires:

- Technical user can snapshot the installed `odoo_ai_assistant` module into the
  private runtime workspace;
- returned public metadata contains logical identities/fingerprints/counts but no
  physical workspace path, `addons_path`, `data_dir` or raw database name;
- inspect rechecks the installed-source fingerprint;
- a User/non-technical account cannot prepare the workspace;
- a different Technical user cannot reuse the id;
- the same Technical user under a different turn cannot reuse the id;
- owner-bound cleanup succeeds;
- no P12 source-edit/patch/test/deploy capability is registered by this slice.

If this fails, repair the smallest owning P12.1 layer and rerun it before P12.2.

## 3. P12.1 acceptance boundary

P12.1 may advance to P12.2 only when the focused dependency-light/static check and the
focused Odoo authority gate are green on a recorded SHA.

Do **not** interpret workspace creation as permission to modify production source.

## 4. Later Phase-12 HARD real gates

These remain unexecuted until the corresponding implementation exists:

```text
P12-REAL-PATH-BOUNDARY
P12-REAL-DIFF-APPROVAL
P12-REAL-TEST-BEFORE-DEPLOY
P12-REAL-DEPLOY-VERIFY
P12-REAL-FAILED-DEPLOY-RECOVERY
```

P12.1 should eventually contribute evidence to `P12-REAL-PATH-BOUNDARY`, but that real
gate is not claimed by dependency-light or focused Odoo tests alone.

## 5. Future-slice binding requirements

P12.2 must bind an approved diff to the exact current workspace fingerprint. P12.3
must bind test results to the exact post-patch workspace fingerprint. P12.4 must refuse
deployment if the installed source fingerprint changed since workspace preparation or
if the approved diff/test receipt belongs to another workspace fingerprint.

An uncertain deployment effect is never retried blindly.

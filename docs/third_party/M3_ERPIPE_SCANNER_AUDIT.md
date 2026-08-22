# M3 ERPipe scanner donor audit

Date: 2026-08-22. Decision: selective design input only; no donor code is
copied by M3-01 or M3-02.

## Audited revision and licensing

- Repository: `https://github.com/erpipe-org/mcp-odoo`.
- Commit: [`f724f97590b9bbe71cb50e59ed68ce94aeb9769e`](https://github.com/erpipe-org/mcp-odoo/commit/f724f97590b9bbe71cb50e59ed68ce94aeb9769e)
  (`chore: release 1.3.2 hosted URL metadata`, committed 2026-08-19).
- Root license: MIT, copyright 2025 Lê Anh Tuấn, in
  [`LICENSE`](https://github.com/erpipe-org/mcp-odoo/blob/f724f97590b9bbe71cb50e59ed68ce94aeb9769e/LICENSE).
- Package metadata also declares MIT in
  [`pyproject.toml`](https://github.com/erpipe-org/mcp-odoo/blob/f724f97590b9bbe71cb50e59ed68ce94aeb9769e/pyproject.toml#L5-L21).
- The relevant Python and test files listed below contain no SPDX identifier,
  copyright line, or different per-file license header. No nested license was
  found for them. The repository-level MIT notice is therefore the applicable
  notice identified by this audit.

If code or a substantial portion is copied later, its destination must retain
the full MIT copyright and permission notice. M3 currently plans clean,
project-specific implementations, so no third-party notice file is added yet.

## File and function inventory

| Donor path / relevant lines | What it provides | Classification | Decision for this product |
| --- | --- | --- | --- |
| [`src/odoo_mcp/agent_tools.py:504-595`](https://github.com/erpipe-org/mcp-odoo/blob/f724f97590b9bbe71cb50e59ed68ce94aeb9769e/src/odoo_mcp/agent_tools.py#L504-L595) `scan_addons_source_report` | Bounded file count/size, extension filtering, symlink skip and dispatch to simple extractors. | `adapt_algorithm` | Keep the ideas of server-side caps, static parsing and symlink rejection. Do not copy: it recursively scans every provided root, returns free-form findings, exposes physical paths and does not filter by installed modules or persist an incremental index. |
| [`src/odoo_mcp/server_core.py:346-384`](https://github.com/erpipe-org/mcp-odoo/blob/f724f97590b9bbe71cb50e59ed68ce94aeb9769e/src/odoo_mcp/server_core.py#L346-L384) `configured_addons_roots` / `restrict_addons_paths` | Resolves operator-configured roots and rejects requested paths outside them. | `adapt_algorithm` | Preserve explicit trusted roots and containment revalidation, but route resolution through this project's deployment profile and never accept model-provided paths. |
| [`src/odoo_mcp/agent_tools.py:645-673`](https://github.com/erpipe-org/mcp-odoo/blob/f724f97590b9bbe71cb50e59ed68ce94aeb9769e/src/odoo_mcp/agent_tools.py#L645-L673) `_normalize_scan_paths` / `_read_manifest` | Environment fallback and `ast.literal_eval` manifest parsing. | `idea_only` | `ast.literal_eval` agrees with the Source of Truth. Implement independently with explicit non-evaluable status and the fields required by M3. Reject the donor's `custom` inference from directory-name prefixes. |
| [`src/odoo_mcp/agent_tools.py:676-940`](https://github.com/erpipe-org/mcp-odoo/blob/f724f97590b9bbe71cb50e59ed68ce94aeb9769e/src/odoo_mcp/agent_tools.py#L676-L940) Python AST helpers | Detects model-like classes, selected methods, `sudo()` text and several compute/CRUD upgrade findings. | `idea_only` | Useful parser test cases, but its output is diagnostics-oriented rather than the required `SourceSymbol` IR. M3 needs `_name`/`_inherit`, fields, methods, decorators, imports and exact end lines, so it will use a clean AST visitor. |
| [`src/odoo_mcp/agent_tools.py:942-984`](https://github.com/erpipe-org/mcp-odoo/blob/f724f97590b9bbe71cb50e59ed68ce94aeb9769e/src/odoo_mcp/agent_tools.py#L942-L984) XML parser | Uses stdlib `ElementTree` and detects only a few record model categories. | `do_not_use` | It does not extract XML ids, inherit relationships, xpath/actions/menus/groups or explicit safe-parser policy. M3 will implement a bounded parser with external entities/network disabled. |
| [`src/odoo_mcp/agent_tools.py:567-575`](https://github.com/erpipe-org/mcp-odoo/blob/f724f97590b9bbe71cb50e59ed68ce94aeb9769e/src/odoo_mcp/agent_tools.py#L567-L575) security CSV handling | Reports that a CSV exists below a directory named `security`. | `do_not_use` | There is no CSV parsing or ACL IR. M3 requires explicit static ACL declarations and must label them as non-runtime permission evidence. |
| Hashing / incremental scan | No scanner hash, mtime cache, stable file fingerprint, stale cleanup or re-scan invalidation was found in the audited scanner path. | `do_not_use` | Implement against the Assistant DB and M3 contracts. The unrelated payload hash and schema cache are not scanner donors. |
| Symbol/source lookup | No `find_symbol`, model-extension lookup, stable source ref or bounded `read_excerpt` implementation was found. | `do_not_use` | Implement later from indexed refs; never expose a free-form file read. |
| [`src/odoo_mcp/tools_diagnostics.py:640-660`](https://github.com/erpipe-org/mcp-odoo/blob/f724f97590b9bbe71cb50e59ed68ce94aeb9769e/src/odoo_mcp/tools_diagnostics.py#L640-L660) and [`src/odoo_mcp/tools_async.py:57-71`](https://github.com/erpipe-org/mcp-odoo/blob/f724f97590b9bbe71cb50e59ed68ce94aeb9769e/src/odoo_mcp/tools_async.py#L57-L71) | MCP tool wrapper, exception flattening and asynchronous job wrapper. | `do_not_use` | M3 does not adopt MCP, the donor's tool architecture or its exception/result surface. Scan lifecycle belongs to this service's application/storage boundaries. |
| [`tests/test_agent_tools.py:501-739`](https://github.com/erpipe-org/mcp-odoo/blob/f724f97590b9bbe71cb50e59ed68ce94aeb9769e/tests/test_agent_tools.py#L501-L739) | Invalid literal, AST syntax, XML error, cap, oversized file and symlink fixtures. | `adapt_algorithm` | Recreate equivalent edge cases independently where they match M3. Add installed-module, provenance, incremental hash and stale cleanup cases absent from the donor. |

## Approved and rejected reuse

Approved as algorithms or test ideas:

- literal-only manifest evaluation;
- Python AST without importing addon code;
- explicit file-count/file-size caps;
- skip and reject symlinks at the source boundary;
- canonical root containment checks;
- parser failures represented as bounded, structured outcomes.

Rejected as implementation or architecture:

- MCP/tool wrappers and the external-credentials connection model;
- unrestricted recursive treatment of every module found in a root;
- physical paths in agent-facing results;
- `custom` provenance inferred from a module/directory name;
- CSV presence as a substitute for ACL parsing;
- non-incremental scan results without fingerprints or stale cleanup;
- free-form dictionaries instead of stable contracts and evidence refs.

## Attribution decision

There are no `reuse_code` entries in this audit. Consequently M3-02 can add
its contracts and persistence without donor attribution in source files. If a
future task changes an entry to `reuse_code`, it must record the destination
path here and add the donor's complete MIT notice before merging.

This decision is narrower than saying the donor scanner is generally reusable:
its safety ideas are relevant, but the current implementation does not satisfy
the product's installed-module, provenance, incremental persistence or stable
evidence-reference requirements.

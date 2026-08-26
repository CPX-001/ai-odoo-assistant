# Dated research snapshots

Despite this directory's historical name, its PDFs are **not** authoritative over current repository code or accepted ADRs.

- `Odoo_AI_Assistant_Source_of_Truth_v1.0.pdf` and `v1.1.pdf` document earlier architecture stages.
- `Odoo_AI_Assistant_Atlas_Referencias_Arquitectonicas_v1.0/v1.1.pdf` are dated architecture/reference research.
- `Odoo_AI_Assistant_Benchmark_Capacidades_Blueprint_v1.0.pdf` is a dated feature/benchmark blueprint.
- `build_source_of_truth_v1_1.py` is document-generation tooling, not runtime code.

The Atlas v1.1 and Benchmark v1.0 already state the correct expiry rule: revalidate against current `main`; code and current ADRs win when the snapshot is older.

Use these files to avoid reinventing studied patterns (Odoo AI, Pydantic AI, FastMCP, Apexive, ERPipe, Viindoo, OCA and others), but verify external sources again before a new architectural decision.

Current entry point: `../README.md`.
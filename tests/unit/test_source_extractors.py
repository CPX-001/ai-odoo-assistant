from pathlib import Path
from uuid import UUID, uuid4

import pytest
from odoo_ai.contracts import (
    ManifestStatus,
    SourceCapabilityState,
    SourceFileKind,
    SourceProvenance,
)
from odoo_ai.source import (
    FileScanContext,
    ManifestExtractor,
    ParserLimits,
    ProvenanceEvidence,
    PythonAstExtractor,
    RootSelection,
    ScanLimits,
    SourceExtractionError,
    SourceScanner,
    StoredSourceFile,
    classify_module_provenance,
    m3_source_extractors,
)

FINGERPRINT = "sha256:" + "a" * 64


def _context(
    content: str | bytes,
    *,
    kind: SourceFileKind,
    logical_path: str,
) -> FileScanContext:
    encoded = content.encode("utf-8") if isinstance(content, str) else content
    return FileScanContext(
        module="sale_fixture",
        logical_path=logical_path,
        kind=kind,
        fingerprint=FINGERPRINT,
        size_bytes=len(encoded),
        mtime_ns=1,
        content=encoded,
    )


def test_literal_manifest_extracts_bounded_metadata_and_assets() -> None:
    source = """{
        'name': 'Sale Fixture',
        'version': '18.0.1.0.0',
        'depends': ['sale', 'project'],
        'data': ['security/ir.model.access.csv', 'views/sale.xml'],
        'assets': {'web.assets_backend': ['sale_fixture/static/src/panel.js',
                  ('after', 'web/static/src/core.js', 'sale_fixture/static/src/after.js')]},
        'license': 'LGPL-3',
    }
    """

    result = ManifestExtractor().extract(
        _context(source, kind=SourceFileKind.MANIFEST, logical_path="sale_fixture/__manifest__.py")
    )

    assert result.metadata is not None
    assert result.metadata["status"] == ManifestStatus.EVALUATED
    assert result.metadata["depends"] == ["sale", "project"]
    assert result.metadata["data"] == [
        "security/ir.model.access.csv",
        "views/sale.xml",
    ]
    assert result.metadata["assets"]["web.assets_backend"][1][0] == "after"


def test_dynamic_manifest_is_unevaluable_and_never_executes_side_effect(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "must-not-exist"
    source = f"__import__('pathlib').Path({str(marker)!r}).write_text('executed')\n"

    result = ManifestExtractor().extract(
        _context(source, kind=SourceFileKind.MANIFEST, logical_path="fixture/__manifest__.py")
    )

    assert result.metadata == {
        "status": "unevaluable",
        "name": None,
        "version": None,
        "depends": [],
        "data": [],
        "assets": {},
        "license": None,
    }
    assert not marker.exists()


def test_python_ast_extracts_models_fields_methods_decorators_imports_and_lines() -> None:
    source = """from odoo import api, fields, models
import logging

class SaleOrder(models.Model):
    _inherit = ['sale.order', 'sale.order.mixin']
    assistant_note = fields.Char()

    @api.model
    def action_confirm(self):
        return super().action_confirm()
"""
    expected_start = source.splitlines().index("    def action_confirm(self):") + 1
    expected_end = source.splitlines().index("        return super().action_confirm()") + 1

    result = PythonAstExtractor().extract(
        _context(
            source,
            kind=SourceFileKind.PYTHON,
            logical_path="sale_fixture/models/sale_order.py",
        )
    )
    action_symbols = [
        symbol
        for symbol in result.symbols
        if symbol.kind == "method" and symbol.name == "action_confirm"
    ]

    assert {(symbol.model, symbol.start_line, symbol.end_line) for symbol in action_symbols} == {
        ("sale.order", expected_start, expected_end),
        ("sale.order.mixin", expected_start, expected_end),
    }
    assert {
        (symbol.kind, symbol.model, symbol.name)
        for symbol in result.symbols
    } >= {
        ("field", "sale.order", "assistant_note"),
        ("inherit", "sale.order", "sale.order"),
        ("decorator", "sale.order", "api.model"),
        ("import", None, "odoo.api"),
        ("import", None, "logging"),
    }


def test_name_takes_method_target_priority_over_inherited_parent() -> None:
    source = """from odoo import models
class NewModel(models.Model):
    _name = 'fixture.new'
    _inherit = 'mail.thread'
    def run(self):
        return True
"""

    result = PythonAstExtractor().extract(
        _context(source, kind=SourceFileKind.PYTHON, logical_path="fixture/models/new.py")
    )

    methods = [symbol for symbol in result.symbols if symbol.kind == "method"]
    assert [(symbol.model, symbol.name) for symbol in methods] == [("fixture.new", "run")]
    assert any(
        symbol.kind == "inherit" and symbol.model == "mail.thread"
        for symbol in result.symbols
    )


def test_syntax_and_node_caps_raise_sanitized_parser_errors() -> None:
    with pytest.raises(SourceExtractionError, match="syntax_error"):
        PythonAstExtractor().extract(
            _context(
                "class Broken(:\n",
                kind=SourceFileKind.PYTHON,
                logical_path="fixture/models/broken.py",
            )
        )

    oversized = _context(
        "{'name': 'too large'}\n",
        kind=SourceFileKind.MANIFEST,
        logical_path="fixture/__manifest__.py",
    )
    with pytest.raises(SourceExtractionError, match="file_too_large"):
        ManifestExtractor(ParserLimits(max_file_bytes=8)).extract(oversized)
    with pytest.raises(SourceExtractionError, match="ast_node_limit_exceeded"):
        PythonAstExtractor(ParserLimits(max_ast_nodes=5)).extract(
            _context(
                "from odoo import models\nclass X(models.Model):\n    _name = 'x'\n",
                kind=SourceFileKind.PYTHON,
                logical_path="fixture/models/x.py",
            )
        )


def test_provenance_uses_explicit_evidence_never_directory_name() -> None:
    assert classify_module_provenance("custom_sale") is SourceProvenance.UNKNOWN
    evidence = ProvenanceEvidence(
        official_modules=frozenset({"sale"}),
        oca_modules=frozenset({"sale_workflow"}),
        manual_rules={"customer_extension": SourceProvenance.MANUAL},
    )
    assert classify_module_provenance("sale", evidence) is SourceProvenance.OFFICIAL
    assert classify_module_provenance("sale_workflow", evidence) is SourceProvenance.OCA
    assert (
        classify_module_provenance("customer_extension", evidence)
        is SourceProvenance.MANUAL
    )
    assert classify_module_provenance("custom", evidence) is SourceProvenance.UNKNOWN


class ExtractorStore:
    def __init__(self) -> None:
        self.files: dict[tuple[str, str], tuple[UUID, str, SourceProvenance]] = {}
        self.symbols: dict[UUID, tuple] = {}
        self.metadata: dict[UUID, dict | None] = {}

    def open_scan(self, *, instance_profile_id: UUID) -> UUID:
        del instance_profile_id
        return uuid4()

    def find_unchanged_file(
        self, *, instance_profile_id, module, logical_path, fingerprint
    ) -> UUID | None:
        del instance_profile_id
        previous = self.files.get((module, logical_path))
        return previous[0] if previous is not None and previous[1] == fingerprint else None

    def upsert_file(
        self,
        *,
        scan_run_id,
        module,
        logical_path,
        kind,
        fingerprint,
        size_bytes,
        provenance,
    ) -> StoredSourceFile:
        del scan_run_id, kind, size_bytes
        key = (module, logical_path)
        previous = self.files.get(key)
        file_id = previous[0] if previous else uuid4()
        changed = previous is None or previous[1] != fingerprint
        self.files[key] = (file_id, fingerprint, provenance)
        return StoredSourceFile(file_id, changed)

    def replace_derivatives(
        self, *, source_file_id, symbols, xml_records, metadata
    ) -> None:
        assert not xml_records
        self.symbols[source_file_id] = symbols
        self.metadata[source_file_id] = metadata

    def mark_stale(self, *, scan_run_id, seen_file_ids) -> int:
        del scan_run_id, seen_file_ids
        return 0

    def delete_stale(self, *, instance_profile_id) -> int:
        del instance_profile_id
        return 0

    def finish_scan(
        self, *, scan_run_id, succeeded, fingerprint, error_code
    ) -> None:
        del scan_run_id, error_code
        assert succeeded and fingerprint is not None

    def record_capability(
        self, *, instance_profile_id, state: SourceCapabilityState
    ) -> None:
        del instance_profile_id
        assert state is SourceCapabilityState.DETECTED


def test_scanner_replaces_removed_method_and_preserves_fingerprint_provenance(
    tmp_path: Path,
) -> None:
    root = tmp_path / "custom" / "addons"
    module = root / "sale_fixture"
    (module / "models").mkdir(parents=True)
    (module / "__manifest__.py").write_text(
        "{'name': 'Fixture', 'depends': ['sale']}\n", encoding="utf-8"
    )
    source_file = module / "models" / "sale_order.py"
    source_file.write_text(
        "from odoo import models\nclass SaleOrder(models.Model):\n"
        "    _inherit = 'sale.order'\n    def action_confirm(self):\n        return True\n",
        encoding="utf-8",
    )
    store = ExtractorStore()
    scanner = SourceScanner(
        store=store,
        extractors=m3_source_extractors(),
        limits=ScanLimits(max_modules=5, max_files=20, max_total_bytes=20_000),
    )
    arguments = {
        "instance_profile_id": uuid4(),
        "roots": RootSelection(override=(root,)),
        "installed_modules": ("sale_fixture",),
        "provenance": {"sale_fixture": SourceProvenance.MANUAL},
    }

    first = scanner.run(**arguments)
    source_file.write_text(
        "from odoo import models\nclass SaleOrder(models.Model):\n"
        "    _inherit = 'sale.order'\n",
        encoding="utf-8",
    )
    second = scanner.run(**arguments)
    python_id, second_hash, provenance = store.files[
        ("sale_fixture", "sale_fixture/models/sale_order.py")
    ]

    assert first.fingerprint != second.fingerprint
    assert second_hash.startswith("sha256:")
    assert provenance is SourceProvenance.MANUAL
    assert not any(symbol.name == "action_confirm" for symbol in store.symbols[python_id])
    manifest_id = store.files[("sale_fixture", "sale_fixture/__manifest__.py")][0]
    assert store.metadata[manifest_id]["status"] == "evaluated"

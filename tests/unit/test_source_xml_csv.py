from pathlib import Path
from uuid import UUID, uuid4

import pytest

from odoo_ai.contracts import SourceCapabilityState, SourceFileKind
from odoo_ai.source import (
    FileScanContext,
    ParserLimits,
    RootSelection,
    SecurityCsvExtractor,
    SourceExtractionError,
    SourceScanner,
    StoredSourceFile,
    XmlExtractor,
    m3_source_extractors,
)


def _context(
    content: str | bytes,
    *,
    kind: SourceFileKind,
    logical_path: str,
) -> FileScanContext:
    encoded = content.encode() if isinstance(content, str) else content
    return FileScanContext(
        module="sale_fixture",
        logical_path=logical_path,
        kind=kind,
        fingerprint="sha256:" + "a" * 64,
        size_bytes=len(encoded),
        mtime_ns=1,
        content=encoded,
    )


def test_xml_extracts_view_inheritance_xpath_action_menu_and_group() -> None:
    result = XmlExtractor().extract(
        _context(
            """<?xml version="1.0"?>
<odoo>
  <record id="view_order_form" model="ir.ui.view">
    <field name="model">sale.order</field>
    <field name="inherit_id" ref="sale.view_order_form"/>
    <field name="arch" type="xml">
      <xpath expr="//button[@name='action_confirm']" position="attributes"/>
    </field>
  </record>
  <record id="action_orders" model="ir.actions.act_window"/>
  <menuitem id="menu_orders" action="action_orders" groups="base.group_user"/>
  <record id="group_sales_reader" model="res.groups"/>
</odoo>
""",
            kind=SourceFileKind.XML,
            logical_path="sale_fixture/views/sale_order.xml",
        )
    )

    records = {record.xml_id: record for record in result.xml_records}
    assert set(records) == {
        "sale_fixture.view_order_form",
        "sale_fixture.action_orders",
        "sale_fixture.menu_orders",
        "sale_fixture.group_sales_reader",
    }
    view = records["sale_fixture.view_order_form"]
    assert view.model == "sale.order"
    assert view.declaration == {
        "declaration_kind": "record",
        "runtime_effective": False,
        "inherit_id": "sale.view_order_form",
        "view_model": "sale.order",
        "xpath": ["//button[@name='action_confirm']"],
    }
    assert view.start_line == 3
    assert view.end_line == 9
    kinds = {(symbol.kind, symbol.name) for symbol in result.symbols}
    assert ("view_inherit", "sale.view_order_form") in kinds
    assert ("xpath", "//button[@name='action_confirm']") in kinds
    assert ("action", "sale_fixture.action_orders") in kinds
    assert ("menu", "sale_fixture.menu_orders") in kinds
    assert ("group", "sale_fixture.group_sales_reader") in kinds
    assert ("group_restriction", "base.group_user") in kinds


def test_xml_rejects_malformed_dtd_depth_and_size() -> None:
    extractor = XmlExtractor()
    with pytest.raises(SourceExtractionError, match="xml_parse_error"):
        extractor.extract(
            _context(
                "<odoo><record id='broken'></odoo>",
                kind=SourceFileKind.XML,
                logical_path="sale_fixture/views/broken.xml",
            )
        )
    hostile = """<!DOCTYPE odoo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<odoo><record id="x" model="x"><field name="name">&xxe;</field></record></odoo>"""
    with pytest.raises(SourceExtractionError, match="xml_forbidden_declaration"):
        extractor.extract(
            _context(
                hostile,
                kind=SourceFileKind.XML,
                logical_path="sale_fixture/views/hostile.xml",
            )
        )
    with pytest.raises(SourceExtractionError, match="xml_depth_limit_exceeded"):
        XmlExtractor(ParserLimits(max_xml_depth=2)).extract(
            _context(
                "<odoo><data><record id='x' model='x'/></data></odoo>",
                kind=SourceFileKind.XML,
                logical_path="sale_fixture/views/deep.xml",
            )
        )
    with pytest.raises(SourceExtractionError, match="file_too_large"):
        XmlExtractor(ParserLimits(max_file_bytes=6)).extract(
            _context(
                "<odoo/>",
                kind=SourceFileKind.XML,
                logical_path="sale_fixture/views/large.xml",
            )
        )


def test_security_csv_is_static_structured_declaration() -> None:
    content = """id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_sale_reader,Sale reader,model_sale_order,base.group_user,1,0,0,0
"""
    result = SecurityCsvExtractor().extract(
        _context(
            content,
            kind=SourceFileKind.CSV,
            logical_path="sale_fixture/security/ir.model.access.csv",
        )
    )

    assert len(result.symbols) == 1
    acl = result.symbols[0]
    assert (acl.kind, acl.model, acl.name, acl.start_line) == (
        "acl",
        "model_sale_order",
        "sale_fixture.access_sale_reader",
        2,
    )
    assert acl.details == {
        "declaration": "static_acl",
        "external_id": "sale_fixture.access_sale_reader",
        "model_external_id": "model_sale_order",
        "group_external_id": "base.group_user",
        "permissions": {
            "read": True,
            "write": False,
            "create": False,
            "unlink": False,
        },
        "runtime_effective": False,
    }


def test_security_csv_rejects_malformed_rows_and_caps() -> None:
    header = "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
    with pytest.raises(SourceExtractionError, match="csv_row_invalid"):
        SecurityCsvExtractor().extract(
            _context(
                header + "broken,row\n",
                kind=SourceFileKind.CSV,
                logical_path="sale_fixture/security/ir.model.access.csv",
            )
        )
    with pytest.raises(SourceExtractionError, match="csv_row_limit_exceeded"):
        SecurityCsvExtractor(ParserLimits(max_csv_rows=1)).extract(
            _context(
                header
                + "a,A,model_a,,1,0,0,0\n"
                + "b,B,model_b,,1,0,0,0\n",
                kind=SourceFileKind.CSV,
                logical_path="sale_fixture/security/access.csv",
            )
        )


class _IndexStore:
    def __init__(self) -> None:
        self.files: dict[tuple[str, str], tuple[UUID, str]] = {}
        self.derivatives: dict[UUID, tuple[tuple, tuple]] = {}
        self.finished: list[tuple[bool, str | None]] = []

    def open_scan(self, *, instance_profile_id: UUID) -> UUID:
        del instance_profile_id
        return uuid4()

    def find_unchanged_file(
        self, *, instance_profile_id, module, logical_path, fingerprint
    ) -> UUID | None:
        del instance_profile_id
        current = self.files.get((module, logical_path))
        return current[0] if current is not None and current[1] == fingerprint else None

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
        del scan_run_id, kind, size_bytes, provenance
        previous = self.files.get((module, logical_path))
        file_id = previous[0] if previous else uuid4()
        changed = previous is None or previous[1] != fingerprint
        self.files[(module, logical_path)] = (file_id, fingerprint)
        return StoredSourceFile(file_id, changed)

    def replace_derivatives(
        self, *, source_file_id, symbols, xml_records, metadata
    ) -> None:
        del metadata
        self.derivatives[source_file_id] = (symbols, xml_records)

    def mark_stale(self, *, scan_run_id, seen_file_ids) -> int:
        del scan_run_id
        stale = [key for key, value in self.files.items() if value[0] not in seen_file_ids]
        for key in stale:
            file_id, fingerprint = self.files[key]
            self.files[key] = (file_id, "stale:" + fingerprint)
        return len(stale)

    def delete_stale(self, *, instance_profile_id) -> int:
        del instance_profile_id
        stale = [key for key, value in self.files.items() if value[1].startswith("stale:")]
        for key in stale:
            file_id = self.files.pop(key)[0]
            self.derivatives.pop(file_id, None)
        return len(stale)

    def finish_scan(self, *, scan_run_id, succeeded, fingerprint, error_code) -> None:
        del scan_run_id, error_code
        self.finished.append((succeeded, fingerprint))

    def record_capability(self, *, instance_profile_id, state) -> None:
        del instance_profile_id, state


def test_partial_scan_preserves_previous_index_and_valid_scan_deletes_stale(
    tmp_path: Path,
) -> None:
    root = tmp_path / "nondefault" / "addons"
    module = root / "sale_fixture"
    (module / "views").mkdir(parents=True)
    (module / "__manifest__.py").write_text("{'name': 'Fixture'}\n", encoding="utf-8")
    view = module / "views" / "sale.xml"
    view.write_text("<odoo><record id='view_sale' model='ir.ui.view'/></odoo>\n")
    store = _IndexStore()
    scanner = SourceScanner(store=store, extractors=m3_source_extractors())
    arguments = {
        "instance_profile_id": uuid4(),
        "roots": RootSelection(override=(root,)),
        "installed_modules": ("sale_fixture",),
    }

    first = scanner.run(**arguments)
    indexed_key = ("sale_fixture", "sale_fixture/views/sale.xml")
    original = store.files[indexed_key]
    view.write_text("<odoo><record id='broken'></odoo>\n")
    partial = scanner.run(**arguments)

    assert first.capability is SourceCapabilityState.DETECTED
    assert partial.capability is SourceCapabilityState.ERROR
    assert any(error.code == "xml_parse_error" for error in partial.errors)
    assert store.files[indexed_key] == original

    view.unlink()
    cleanup = scanner.run(**arguments)
    assert cleanup.capability is SourceCapabilityState.DETECTED
    assert cleanup.metrics.stale_files == 1
    assert indexed_key not in store.files
    assert original[0] not in store.derivatives

    uninstalled = scanner.run(
        instance_profile_id=arguments["instance_profile_id"],
        roots=arguments["roots"],
        installed_modules=(),
    )
    assert uninstalled.capability is SourceCapabilityState.DETECTED
    assert uninstalled.metrics.stale_files >= 1
    assert store.files == {}

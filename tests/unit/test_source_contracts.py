from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from odoo_ai.contracts import (
    InstanceInventory,
    ScanRun,
    ScanStatus,
    SourceFile,
    SourceFileKind,
    SourceRef,
    SourceSymbol,
    XmlRecord,
    export_public_json_schemas,
)

SCAN_ID = UUID("12345678-1234-5678-1234-567812345678")
FILE_ID = UUID("22345678-1234-5678-1234-567812345678")
SYMBOL_ID = UUID("32345678-1234-5678-1234-567812345678")
XML_ID = UUID("42345678-1234-5678-1234-567812345678")
FINGERPRINT = "sha256:" + "a" * 64
NOW = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)


def test_source_contracts_represent_stable_structural_pointers() -> None:
    source_file = SourceFile(
        file_id=FILE_ID,
        scan_id=SCAN_ID,
        instance_id="odoo-test",
        module="custom_sale",
        kind=SourceFileKind.PYTHON,
        logical_path="custom_sale/models/sale_order.py",
        fingerprint=FINGERPRINT,
        size_bytes=4096,
    )
    ref = SourceRef(
        source_file_id=source_file.file_id,
        fingerprint=source_file.fingerprint,
        start_line=42,
        end_line=71,
    )
    symbol = SourceSymbol(
        symbol_id=SYMBOL_ID,
        module=source_file.module,
        kind="method",
        model="sale.order",
        name="action_confirm",
        logical_path=source_file.logical_path,
        start_line=42,
        end_line=71,
        fingerprint=source_file.fingerprint,
        ref=ref,
    )
    xml_record = XmlRecord(
        record_id=XML_ID,
        module="custom_sale",
        xml_id="custom_sale.view_order_form",
        model="ir.ui.view",
        logical_path="custom_sale/views/sale_order.xml",
        fingerprint=FINGERPRINT,
        ref=SourceRef(source_file_id=FILE_ID, fingerprint=FINGERPRINT),
    )

    assert symbol.ref.source_file_id == source_file.file_id
    assert symbol.end_line == 71
    assert xml_record.model == "ir.ui.view"


def test_scan_lifecycle_and_source_pointer_invariants_are_validated() -> None:
    running = ScanRun(
        scan_id=SCAN_ID,
        instance_id="odoo-test",
        status=ScanStatus.RUNNING,
        started_at=NOW,
    )
    completed = running.model_copy(
        update={"status": ScanStatus.SUCCEEDED, "completed_at": NOW}
    )

    assert running.completed_at is None
    assert completed.status is ScanStatus.SUCCEEDED

    with pytest.raises(ValidationError):
        ScanRun(
            scan_id=SCAN_ID,
            instance_id="odoo-test",
            status=ScanStatus.FAILED,
            started_at=NOW,
        )
    with pytest.raises(ValidationError):
        SourceRef(
            source_file_id=FILE_ID,
            fingerprint=FINGERPRINT,
            start_line=8,
        )


@pytest.mark.parametrize(
    "logical_path",
    ["/opt/odoo/addons/module.py", "../module.py", "module\\models.py"],
)
def test_source_file_rejects_physical_or_escaping_paths(logical_path: str) -> None:
    with pytest.raises(ValidationError):
        SourceFile(
            file_id=FILE_ID,
            scan_id=SCAN_ID,
            instance_id="odoo-test",
            module="custom_sale",
            kind=SourceFileKind.PYTHON,
            logical_path=logical_path,
            fingerprint=FINGERPRINT,
            size_bytes=10,
        )


def test_source_contracts_are_in_public_json_schema_export() -> None:
    schemas = export_public_json_schemas()

    assert {
        "InstanceInventory",
        "ManifestMetadata",
        "ScanRun",
        "SourceFile",
        "SourceRef",
        "SourceSymbol",
        "XmlRecord",
    } <= schemas.keys()


def test_instance_inventory_is_bounded_and_deduplicated() -> None:
    inventory = InstanceInventory(
        database="customer_odoo",
        server_version="18.0",
        installed_modules=("base", "sale"),
        addons_roots=("/srv/customer/addons",),
        captured_at=NOW,
    )

    assert inventory.installed_modules == ("base", "sale")
    with pytest.raises(ValidationError):
        InstanceInventory(
            database="customer_odoo",
            server_version="18.0",
            installed_modules=("base", "base"),
            addons_roots=("/srv/customer/addons",),
            captured_at=NOW,
        )

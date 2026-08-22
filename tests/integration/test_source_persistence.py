import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session

from odoo_ai.contracts import (
    EvidenceStatus,
    FindModelExtensionsRequest,
    FindSymbolRequest,
    ReadExcerptRequest,
    SourceRef,
)
from odoo_ai.source import (
    RootSelection,
    SourceEvidenceService,
    SourceQueryError,
    SourceScanner,
    SqlAlchemySourceScanStore,
    m3_source_extractors,
    resolve_source_roots,
)
from odoo_ai.storage import (
    DatabaseSettings,
    SourceSymbolValues,
    XmlRecordValues,
    create_database_engine,
    create_instance_profile,
    delete_stale_source_files,
    find_source_symbols,
    find_xml_records,
    finish_scan,
    mark_stale_source_files,
    open_scan,
    replace_file_derivatives,
    upsert_source_file,
)
from odoo_ai.storage.config import DATABASE_NAME_ENV, DATABASE_URL_ENV

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL_ENV = "ODOO_AI_TEST_DATABASE_URL"
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


@pytest.fixture
def migrated_engine(monkeypatch: pytest.MonkeyPatch) -> Engine:
    test_url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not test_url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is not configured")
    database_name = test_url.rsplit("/", maxsplit=1)[-1].partition("?")[0]
    monkeypatch.setenv(DATABASE_URL_ENV, test_url)
    monkeypatch.setenv(DATABASE_NAME_ENV, database_name)
    command.upgrade(Config(REPO_ROOT / "alembic.ini"), "head")
    engine = create_database_engine(DatabaseSettings.from_env())
    yield engine
    engine.dispose()


@pytest.fixture
def session(migrated_engine: Engine) -> Session:
    with migrated_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def _profile(session: Session):
    return create_instance_profile(
        session,
        instance_id=f"source-{uuid4()}",
        fingerprint="sha256:instance",
    )


def _upsert_python(session: Session, scan_id: UUID, fingerprint: str, path: str):
    return upsert_source_file(
        session,
        scan_run_id=scan_id,
        module="custom_sale",
        logical_path=path,
        kind="python",
        fingerprint=fingerprint,
        size_bytes=2048,
    )


def test_source_tables_constraints_and_indexes_exist(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)

    assert {"scan_run", "source_file", "source_symbol", "xml_record"} <= set(
        inspector.get_table_names()
    )
    assert {index["name"] for index in inspector.get_indexes("scan_run")} >= {
        "ix_scan_run_instance_status_started"
    }
    assert {index["name"] for index in inspector.get_indexes("source_file")} >= {
        "ix_source_file_fingerprint",
        "ix_source_file_instance_module",
    }
    assert {column["name"] for column in inspector.get_columns("source_file")} >= {
        "provenance",
        "extracted_metadata",
    }
    assert "details" in {
        column["name"] for column in inspector.get_columns("source_symbol")
    }
    assert "declaration" in {
        column["name"] for column in inspector.get_columns("xml_record")
    }
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("source_file")
    } >= {"uq_source_file_instance_module_path"}
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("source_symbol")
    } >= {"uq_source_symbol_file_identity"}
    symbol_identity = next(
        constraint
        for constraint in inspector.get_unique_constraints("source_symbol")
        if constraint["name"] == "uq_source_symbol_file_identity"
    )
    assert "model" in symbol_identity["column_names"]
    assert {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("xml_record")
    } >= {"uq_xml_record_file_xml_id"}
    assert {index["name"] for index in inspector.get_indexes("source_symbol")} >= {
        "ix_source_symbol_model_name",
        "ix_source_symbol_module_path",
    }
    assert {index["name"] for index in inspector.get_indexes("xml_record")} >= {
        "ix_xml_record_module_path",
        "ix_xml_record_xml_id_model",
    }


def test_changed_fingerprint_hides_then_replaces_file_derivatives(session: Session) -> None:
    profile = _profile(session)
    first_scan = open_scan(session, instance_profile_id=profile.id)
    first = _upsert_python(
        session,
        first_scan.id,
        HASH_A,
        "custom_sale/models/sale_order.py",
    )
    symbols, xml_records = replace_file_derivatives(
        session,
        source_file_id=first.file.id,
        symbols=[
            SourceSymbolValues(
                kind="method",
                model="sale.order",
                name="action_confirm",
                start_line=42,
                end_line=71,
            )
        ],
        xml_records=[
            XmlRecordValues(
                xml_id="custom_sale.view_order_form",
                model="ir.ui.view",
                start_line=3,
                end_line=12,
            )
        ],
        extracted_metadata={"parser": "python_ast"},
    )
    finish_scan(session, scan_run_id=first_scan.id, status="succeeded", fingerprint=HASH_A)

    assert first.fingerprint_changed is True
    assert symbols[0].fingerprint == HASH_A
    assert first.file.extracted_metadata == {"parser": "python_ast"}
    assert first.file.provenance == "unknown"
    assert xml_records[0].fingerprint == HASH_A
    assert len(
        find_source_symbols(
            session,
            instance_profile_id=profile.id,
            model="sale.order",
            name="action_confirm",
        )
    ) == 1

    second_scan = open_scan(session, instance_profile_id=profile.id)
    changed = _upsert_python(
        session,
        second_scan.id,
        HASH_B,
        "custom_sale/models/sale_order.py",
    )

    assert changed.file.id == first.file.id
    assert changed.fingerprint_changed is True
    assert (
        find_source_symbols(
            session,
            instance_profile_id=profile.id,
            name="action_confirm",
        )
        == []
    )
    assert (
        find_xml_records(
            session,
            instance_profile_id=profile.id,
            xml_id="custom_sale.view_order_form",
        )
        == []
    )

    replacement, _ = replace_file_derivatives(
        session,
        source_file_id=changed.file.id,
        symbols=[
            SourceSymbolValues(
                kind="method",
                model="sale.order",
                name="action_confirm",
                start_line=50,
                end_line=80,
            )
        ],
        xml_records=[],
    )
    finish_scan(session, scan_run_id=second_scan.id, status="succeeded", fingerprint=HASH_B)

    assert replacement[0].fingerprint == HASH_B
    assert replacement[0].start_line == 50
    assert len(
        find_source_symbols(
            session,
            instance_profile_id=profile.id,
            name="action_confirm",
        )
    ) == 1


def test_stale_mark_and_delete_cascade_removed_derivatives(session: Session) -> None:
    profile = _profile(session)
    first_scan = open_scan(session, instance_profile_id=profile.id)
    kept = _upsert_python(
        session, first_scan.id, HASH_A, "custom_sale/models/kept.py"
    )
    removed = _upsert_python(
        session, first_scan.id, HASH_A, "custom_sale/models/removed.py"
    )
    replace_file_derivatives(
        session,
        source_file_id=removed.file.id,
        symbols=[
            SourceSymbolValues(
                kind="method",
                model="sale.order",
                name="removed_method",
                start_line=2,
                end_line=4,
            )
        ],
        xml_records=[],
    )
    finish_scan(session, scan_run_id=first_scan.id, status="succeeded", fingerprint=HASH_A)

    second_scan = open_scan(session, instance_profile_id=profile.id)
    seen = _upsert_python(session, second_scan.id, HASH_A, kept.file.logical_path)
    marked = mark_stale_source_files(
        session, scan_run_id=second_scan.id, seen_file_ids={seen.file.id}
    )

    assert marked == 1
    assert (
        find_source_symbols(
            session,
            instance_profile_id=profile.id,
            name="removed_method",
        )
        == []
    )
    assert delete_stale_source_files(session, instance_profile_id=profile.id) == 1
    finish_scan(session, scan_run_id=second_scan.id, status="succeeded", fingerprint=HASH_A)


def test_scan_lifecycle_and_structured_query_limits(session: Session) -> None:
    profile = _profile(session)
    scan = open_scan(session, instance_profile_id=profile.id)

    with pytest.raises(ValueError, match="identifier"):
        find_source_symbols(session, instance_profile_id=profile.id)
    with pytest.raises(ValueError, match="between"):
        find_xml_records(
            session,
            instance_profile_id=profile.id,
            xml_id="module.record",
            limit=201,
        )

    finish_scan(session, scan_run_id=scan.id, status="failed", error_code="partial_scan")
    with pytest.raises(ValueError, match="already finished"):
        finish_scan(session, scan_run_id=scan.id, status="failed")


def test_real_scanner_indexes_and_replaces_action_confirm(
    session: Session, tmp_path: Path
) -> None:
    root = tmp_path / "nondefault" / "extensions"
    module = root / "sale_fixture"
    (module / "models").mkdir(parents=True)
    (module / "views").mkdir()
    (module / "security").mkdir()
    (module / "__manifest__.py").write_text(
        "{'name': 'Fixture', 'depends': ['sale']}\n", encoding="utf-8"
    )
    source = module / "models" / "sale_order.py"
    source.write_text(
        "from odoo import models\nclass SaleOrder(models.Model):\n"
        "    _inherit = 'sale.order'\n    def action_confirm(self):\n        return True\n",
        encoding="utf-8",
    )
    view = module / "views" / "sale_order.xml"
    view.write_text(
        "<odoo>\n  <record id='view_order_form' model='ir.ui.view'>\n"
        "    <field name='model'>sale.order</field>\n"
        "    <field name='inherit_id' ref='sale.view_order_form'/>\n"
        "  </record>\n</odoo>\n",
        encoding="utf-8",
    )
    access = module / "security" / "ir.model.access.csv"
    access.write_text(
        "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
        "access_sale_reader,Reader,model_sale_order,base.group_user,1,0,0,0\n",
        encoding="utf-8",
    )
    profile = _profile(session)
    scanner = SourceScanner(
        store=SqlAlchemySourceScanStore(session),
        extractors=m3_source_extractors(),
    )
    arguments = {
        "instance_profile_id": profile.id,
        "roots": RootSelection(override=(root,)),
        "installed_modules": ("sale_fixture",),
    }

    scanner.run(**arguments)
    symbols = find_source_symbols(
        session,
        instance_profile_id=profile.id,
        model="sale.order",
        name="action_confirm",
    )

    assert len(symbols) == 1
    assert (symbols[0].start_line, symbols[0].end_line) == (4, 5)
    assert symbols[0].fingerprint.startswith("sha256:")
    xml_records = find_xml_records(
        session,
        instance_profile_id=profile.id,
        xml_id="sale_fixture.view_order_form",
    )
    assert len(xml_records) == 1
    assert xml_records[0].declaration["inherit_id"] == "sale.view_order_form"
    acl_symbols = find_source_symbols(
        session,
        instance_profile_id=profile.id,
        name="sale_fixture.access_sale_reader",
    )
    assert len(acl_symbols) == 1
    assert acl_symbols[0].kind == "acl"
    assert acl_symbols[0].details["runtime_effective"] is False

    source.write_text(
        "from odoo import models\nclass SaleOrder(models.Model):\n"
        "    _inherit = 'sale.order'\n",
        encoding="utf-8",
    )
    scanner.run(**arguments)

    assert find_source_symbols(
        session,
        instance_profile_id=profile.id,
        model="sale.order",
        name="action_confirm",
    ) == []

    view.unlink()
    scanner.run(**arguments)
    assert find_xml_records(
        session,
        instance_profile_id=profile.id,
        xml_id="sale_fixture.view_order_form",
    ) == []


def test_source_queries_and_checked_excerpt_are_bounded_and_current(
    session: Session, tmp_path: Path
) -> None:
    root = tmp_path / "customer" / "extensions"
    module = root / "sale_fixture"
    (module / "models").mkdir(parents=True)
    (module / "views").mkdir()
    (module / "__manifest__.py").write_text("{'name': 'Fixture'}\n", encoding="utf-8")
    source = module / "models" / "sale_order.py"
    original = (
        "from odoo import models\n"
        "class SaleOrder(models.Model):\n"
        "    _inherit = 'sale.order'\n"
        "    def action_confirm(self):\n"
        "        return super().action_confirm()\n"
    )
    source.write_text(original, encoding="utf-8")
    (module / "models" / "sale_order_extra.py").write_text(
        original.replace("SaleOrder", "SaleOrderExtra"), encoding="utf-8"
    )
    (module / "views" / "sale_order.xml").write_text(
        "<odoo>\n"
        "  <record id='view_order_form' model='ir.ui.view'>\n"
        "    <field name='model'>sale.order</field>\n"
        "  </record>\n"
        "</odoo>\n",
        encoding="utf-8",
    )
    profile = _profile(session)
    selection = RootSelection(override=(root,))
    scanner = SourceScanner(
        store=SqlAlchemySourceScanStore(session), extractors=m3_source_extractors()
    )
    result = scanner.run(
        instance_profile_id=profile.id,
        roots=selection,
        installed_modules=("sale_fixture",),
    )
    assert result.capability.value == "DETECTED"
    resolved_roots = resolve_source_roots(selection).roots
    service = SourceEvidenceService(session=session, roots=resolved_roots)

    exact = service.find_symbol(
        instance_profile_id=profile.id,
        request=FindSymbolRequest(
            query="action_confirm", model="sale.order", max_results=1
        ),
    )
    normalized = service.find_symbol(
        instance_profile_id=profile.id,
        request=FindSymbolRequest(query="action-confirm", model="sale.order"),
    )
    xml = service.find_symbol(
        instance_profile_id=profile.id,
        request=FindSymbolRequest(query="sale_fixture.view_order_form"),
    )
    unknown = service.find_symbol(
        instance_profile_id=profile.id,
        request=FindSymbolRequest(query="does_not_exist"),
    )

    assert len(exact.candidates) == 1
    candidate = exact.candidates[0]
    assert (candidate.kind, candidate.start_line, candidate.end_line) == (
        "method",
        4,
        5,
    )
    assert candidate.match_reason.value == "exact"
    assert len(normalized.candidates) == 2
    assert normalized.candidates[0].match_reason.value == "normalized"
    assert xml.candidates[0].kind == "xml_id"
    assert unknown.candidates == ()

    extensions = service.find_model_extensions(
        instance_profile_id=profile.id,
        request=FindModelExtensionsRequest(model="sale.order"),
    )
    assert len(extensions.groups) == 2
    assert all(group.runtime_order_checked is False for group in extensions.groups)
    assert {
        item.kind for group in extensions.groups for item in group.relationships
    } == {"inherit"}

    excerpt = service.read_excerpt(
        instance_profile_id=profile.id,
        request=ReadExcerptRequest(
            ref=candidate.ref,
            context_before=1,
            context_after=0,
            max_lines=3,
            max_bytes=512,
        ),
    )
    assert [(line.number, line.text) for line in excerpt.lines] == [
        (3, "    _inherit = 'sale.order'"),
        (4, "    def action_confirm(self):"),
        (5, "        return super().action_confirm()"),
    ]
    assert excerpt.evidence.status is EvidenceStatus.CHECKED
    assert excerpt.evidence.fingerprint == candidate.fingerprint
    assert excerpt.evidence.payload["trust"] == "untrusted_source"
    assert len(excerpt.model_dump_json().encode()) <= 2048

    with pytest.raises(ValidationError):
        ReadExcerptRequest.model_validate(
            {"ref": candidate.ref.model_dump(mode="json"), "path": "/etc/passwd"}
        )
    with pytest.raises(SourceQueryError, match="source_ref_invalid"):
        service.read_excerpt(
            instance_profile_id=profile.id,
            request=ReadExcerptRequest(
                ref=SourceRef(
                    source_file_id=uuid4(),
                    fingerprint=candidate.fingerprint,
                    start_line=4,
                    end_line=5,
                )
            ),
        )
    with pytest.raises(SourceQueryError, match="source_ref_invalid"):
        service.read_excerpt(
            instance_profile_id=profile.id,
            request=ReadExcerptRequest(
                ref=candidate.ref.model_copy(
                    update={"start_line": 3, "end_line": 5}
                )
            ),
        )

    source.write_text(original.replace("return super()", "return False or super()"))
    with pytest.raises(SourceQueryError, match="stale_source"):
        service.read_excerpt(
            instance_profile_id=profile.id,
            request=ReadExcerptRequest(ref=candidate.ref),
        )

    source.write_text(original, encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text(original, encoding="utf-8")
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(SourceQueryError, match="source_path_escape"):
        service.read_excerpt(
            instance_profile_id=profile.id,
            request=ReadExcerptRequest(ref=candidate.ref),
        )

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session

from odoo_ai.knowledge import (
    FilesystemKnowledgeLimits,
    FilesystemKnowledgeProvider,
    KnowledgeIngestionService,
    KnowledgeSourceConfig,
    SqlAlchemyKnowledgeIngestStore,
)
from odoo_ai.storage import (
    DatabaseSettings,
    create_database_engine,
    create_instance_profile,
    get_knowledge_document,
    list_knowledge_chunks,
)
from odoo_ai.storage.config import DATABASE_NAME_ENV, DATABASE_URL_ENV

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL_ENV = "ODOO_AI_TEST_DATABASE_URL"


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


def test_knowledge_tables_and_fts_indexes_exist(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    assert {"knowledge_document", "knowledge_chunk"} <= set(inspector.get_table_names())
    assert {index["name"] for index in inspector.get_indexes("knowledge_document")} >= {
        "ix_knowledge_document_fingerprint",
        "ix_knowledge_document_instance_provider_status",
    }
    chunk_indexes = {index["name"]: index for index in inspector.get_indexes("knowledge_chunk")}
    assert {"ix_knowledge_chunk_document", "ix_knowledge_chunk_search_vector"} <= set(chunk_indexes)
    assert (
        chunk_indexes["ix_knowledge_chunk_search_vector"]["dialect_options"]["postgresql_using"]
        == "gin"
    )


def test_incremental_ingestion_change_fts_and_retirement(session: Session, tmp_path: Path) -> None:
    root = tmp_path / "non-default knowledge root"
    root.mkdir()
    document_path = root / "payments.md"
    document_path.write_text(
        "# Plazos de pago\n\nConfigura cobertura comercial y vencimiento.\n",
        encoding="utf-8",
    )
    profile = create_instance_profile(
        session,
        instance_id=f"knowledge-{uuid4()}",
        fingerprint="sha256:knowledge-instance",
    )
    provider = FilesystemKnowledgeProvider(
        KnowledgeSourceConfig(provider_id="customer.docs", root=root, locale="es-ES")
    )
    service = KnowledgeIngestionService(
        store=SqlAlchemyKnowledgeIngestStore(session), fts_config="simple"
    )

    first = service.ingest(instance_profile_id=profile.id, provider=provider)
    stored = get_knowledge_document(
        session,
        instance_profile_id=profile.id,
        provider_id="customer.docs",
        document_id="payments.md",
    )
    assert stored is not None
    first_fingerprint = stored.fingerprint
    first_chunks = list_knowledge_chunks(session, knowledge_document_id=stored.id)
    first_chunk_ids = [chunk.id for chunk in first_chunks]
    assert first.metrics.documents_indexed == 1
    assert first.metrics.documents_unchanged == 0
    assert first.metrics.chunks == len(first_chunks) > 0
    assert str(root) not in first.model_dump_json()

    match_count = session.scalar(
        text(
            "SELECT count(*) FROM knowledge_chunk kc "
            "JOIN knowledge_document kd ON kd.id = kc.knowledge_document_id "
            "WHERE kd.status = 'current' "
            "AND kc.search_vector @@ plainto_tsquery('simple'::regconfig, :query)"
        ),
        {"query": "cobertura"},
    )
    assert match_count == 1

    second = service.ingest(instance_profile_id=profile.id, provider=provider)
    second_chunks = list_knowledge_chunks(session, knowledge_document_id=stored.id)
    assert second.metrics.documents_indexed == 0
    assert second.metrics.documents_unchanged == 1
    assert [chunk.id for chunk in second_chunks] == first_chunk_ids

    document_path.write_text(
        "# Plazos de pago\n\nConfigura anticipos y vencimientos actualizados.\n",
        encoding="utf-8",
    )
    changed = service.ingest(instance_profile_id=profile.id, provider=provider)
    session.refresh(stored)
    changed_chunks = list_knowledge_chunks(session, knowledge_document_id=stored.id)
    assert changed.metrics.documents_indexed == 1
    assert stored.fingerprint != first_fingerprint
    assert [chunk.id for chunk in changed_chunks] != first_chunk_ids
    assert all(chunk.document_fingerprint == stored.fingerprint for chunk in changed_chunks)

    document_path.unlink()
    retired = service.ingest(instance_profile_id=profile.id, provider=provider)
    session.refresh(stored)
    assert retired.metrics.documents_retired == 1
    assert stored.status == "retired"
    active_matches = session.scalar(
        text(
            "SELECT count(*) FROM knowledge_chunk kc "
            "JOIN knowledge_document kd ON kd.id = kc.knowledge_document_id "
            "WHERE kd.status = 'current' AND kc.search_vector @@ "
            "plainto_tsquery('simple'::regconfig, 'anticipos')"
        )
    )
    assert active_matches == 0


def test_incomplete_scan_does_not_retire_unseen_documents(session: Session, tmp_path: Path) -> None:
    root = tmp_path / "partial"
    root.mkdir()
    (root / "a.txt").write_text("first", encoding="utf-8")
    (root / "b.txt").write_text("second", encoding="utf-8")
    profile = create_instance_profile(
        session,
        instance_id=f"partial-{uuid4()}",
        fingerprint="sha256:partial-instance",
    )
    store = SqlAlchemyKnowledgeIngestStore(session)
    full_provider = FilesystemKnowledgeProvider(
        KnowledgeSourceConfig(provider_id="partial", root=root)
    )
    service = KnowledgeIngestionService(store=store)
    service.ingest(instance_profile_id=profile.id, provider=full_provider)

    (root / "a.txt").unlink()
    (root / "c.txt").write_text("third", encoding="utf-8")
    limited_provider = FilesystemKnowledgeProvider(
        KnowledgeSourceConfig(provider_id="partial", root=root),
        limits=FilesystemKnowledgeLimits(max_documents=1),
    )
    result = service.ingest(instance_profile_id=profile.id, provider=limited_provider)

    unseen = get_knowledge_document(
        session,
        instance_profile_id=profile.id,
        provider_id="partial",
        document_id="a.txt",
    )
    assert not result.complete
    assert result.metrics.documents_retired == 0
    assert unseen is not None and unseen.status == "current"

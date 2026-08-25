import json
from pathlib import Path

import pytest
from odoo_ai.contracts import KnowledgeDocument, KnowledgeMediaType
from odoo_ai.knowledge import (
    KNOWLEDGE_SOURCES_ENV,
    FilesystemKnowledgeLimits,
    FilesystemKnowledgeProvider,
    KnowledgeChunkingError,
    KnowledgeChunkLimits,
    KnowledgeSourceConfig,
    chunk_document,
    knowledge_sources_from_env,
)
from pydantic import ValidationError


def test_nondefault_root_and_unicode_markdown_are_bounded_and_logical(
    tmp_path: Path,
) -> None:
    root = tmp_path / "customer docs" / "manuales"
    root.mkdir(parents=True)
    physical_path = root / "cobros.md"
    physical_path.write_text(
        "# Configuración de cobros\n\nUsa el plazo de pago ágil.\n", encoding="utf-8"
    )

    provider = FilesystemKnowledgeProvider(
        KnowledgeSourceConfig(provider_id="customer.manual", root=root, locale="es-ES")
    )
    result = provider.scan()

    assert result.complete
    assert result.issues == ()
    assert len(result.documents) == 1
    document = result.documents[0]
    assert document.document_id == "cobros.md"
    assert document.title == "Configuración de cobros"
    assert document.locale == "es-ES"
    assert document.media_type is KnowledgeMediaType.MARKDOWN
    assert document.size_bytes == len(document.content.encode("utf-8"))
    serialized = result.model_dump_json()
    assert str(root) not in serialized
    assert str(physical_path) not in serialized


def test_environment_override_is_explicit_and_rejects_ambiguous_values(
    tmp_path: Path,
) -> None:
    payload = json.dumps([{"provider_id": "ops", "root": str(tmp_path), "locale": "en-GB"}])
    configs = knowledge_sources_from_env({KNOWLEDGE_SOURCES_ENV: payload})
    assert configs == (KnowledgeSourceConfig(provider_id="ops", root=tmp_path, locale="en-GB"),)
    assert knowledge_sources_from_env({}) == ()

    with pytest.raises(ValueError, match="unique"):
        knowledge_sources_from_env(
            {
                KNOWLEDGE_SOURCES_ENV: json.dumps(
                    [
                        {"provider_id": "ops", "root": str(tmp_path)},
                        {"provider_id": "ops", "root": str(tmp_path / "other")},
                    ]
                )
            }
        )
    with pytest.raises(ValueError, match="normalized"):
        KnowledgeSourceConfig(provider_id="ops", root=tmp_path / ".." / tmp_path.name)


def test_symlink_binary_and_unsupported_files_never_escape_root(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# Secret\nshould not be read", encoding="utf-8")
    (root / "escape.md").symlink_to(outside)
    (root / "binary.txt").write_bytes(b"safe\0hidden")
    (root / "ignored.pdf").write_bytes(b"%PDF-not-supported")

    result = FilesystemKnowledgeProvider(
        KnowledgeSourceConfig(provider_id="safe", root=root)
    ).scan()

    assert result.documents == ()
    assert {issue.code for issue in result.issues} == {
        "binary_ignored",
        "symlink_rejected",
    }
    assert all(issue.document_id != "ignored.pdf" for issue in result.issues)


def test_filesystem_caps_fail_partial_without_unbounded_read(tmp_path: Path) -> None:
    root = tmp_path / "bounded"
    root.mkdir()
    (root / "a.txt").write_text("12345", encoding="utf-8")
    (root / "b.txt").write_text("67890", encoding="utf-8")

    file_limited = FilesystemKnowledgeProvider(
        KnowledgeSourceConfig(provider_id="file-cap", root=root),
        limits=FilesystemKnowledgeLimits(max_file_bytes=4),
    ).scan()
    assert file_limited.documents == ()
    assert [issue.code for issue in file_limited.issues] == [
        "file_bytes_limit",
        "file_bytes_limit",
    ]

    document_limited = FilesystemKnowledgeProvider(
        KnowledgeSourceConfig(provider_id="doc-cap", root=root),
        limits=FilesystemKnowledgeLimits(max_documents=1),
    ).scan()
    assert not document_limited.complete
    assert len(document_limited.documents) == 1
    assert document_limited.issues[-1].code == "document_limit"

    total_limited = FilesystemKnowledgeProvider(
        KnowledgeSourceConfig(provider_id="total-cap", root=root),
        limits=FilesystemKnowledgeLimits(max_total_bytes=6),
    ).scan()
    assert not total_limited.complete
    assert len(total_limited.documents) == 1
    assert total_limited.issues[-1].code == "total_bytes_limit"


def test_chunking_is_deterministic_and_honors_char_byte_line_caps(
    tmp_path: Path,
) -> None:
    root = tmp_path / "chunks"
    root.mkdir()
    (root / "unicode.txt").write_text("áéí\nsegunda línea\nfin", encoding="utf-8")
    document = (
        FilesystemKnowledgeProvider(
            KnowledgeSourceConfig(provider_id="chunks", root=root, locale="es")
        )
        .scan()
        .documents[0]
    )
    limits = KnowledgeChunkLimits(max_chars=8, max_bytes=10)

    first = chunk_document(document, limits=limits)
    second = chunk_document(document, limits=limits)

    assert first == second
    assert "".join(chunk.content for chunk in first) == document.content
    assert [chunk.ordinal for chunk in first] == list(range(len(first)))
    assert all(chunk.char_count <= 8 and chunk.byte_count <= 10 for chunk in first)
    assert all(chunk.start_line <= chunk.end_line for chunk in first)

    with pytest.raises(KnowledgeChunkingError, match="knowledge_chunk_limit"):
        chunk_document(
            document,
            limits=KnowledgeChunkLimits(max_chars=1, max_bytes=4, max_chunks=1),
        )


def test_contract_rejects_physical_or_escaping_document_ids(tmp_path: Path) -> None:
    document = FilesystemKnowledgeProvider(
        KnowledgeSourceConfig(provider_id="contracts", root=tmp_path)
    ).scan()
    assert document.documents == ()

    common = {
        "provider_id": "contracts",
        "title": "Unsafe",
        "locale": None,
        "media_type": "text/plain",
        "content": "value",
        "fingerprint": "sha256:" + "a" * 64,
        "size_bytes": 5,
        "observed_at": "2026-08-23T10:00:00Z",
    }
    for document_id in ("../secret.txt", "/etc/passwd", "folder\\secret.txt"):
        with pytest.raises(ValidationError):
            KnowledgeDocument.model_validate({**common, "document_id": document_id})

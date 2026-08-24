from pathlib import Path
from uuid import UUID, uuid4

from odoo_ai.contracts import SourceCapabilityState, SourceFileKind
from odoo_ai.source import (
    FileExtraction,
    RootSelection,
    ScanLimits,
    SourceExtractionError,
    SourceScanner,
    StoredSourceFile,
)


class Store:
    def __init__(self) -> None:
        self.files: dict[tuple[str, str], UUID] = {}
        self.mark_stale_calls = 0
        self.finished: tuple[bool, str | None] | None = None

    def open_scan(self, *, instance_profile_id: UUID) -> UUID:
        del instance_profile_id
        return uuid4()

    def find_unchanged_file(self, **kwargs) -> UUID | None:
        del kwargs
        return None

    def upsert_file(
        self,
        *,
        scan_run_id: UUID,
        module: str,
        logical_path: str,
        kind: SourceFileKind,
        fingerprint: str,
        size_bytes: int,
        provenance,
    ) -> StoredSourceFile:
        del scan_run_id, kind, fingerprint, size_bytes, provenance
        file_id = uuid4()
        self.files[(module, logical_path)] = file_id
        return StoredSourceFile(file_id=file_id, fingerprint_changed=True)

    def replace_derivatives(self, **kwargs) -> None:
        del kwargs

    def mark_stale(self, *, scan_run_id: UUID, seen_file_ids: set[UUID]) -> int:
        del scan_run_id, seen_file_ids
        self.mark_stale_calls += 1
        return 0

    def delete_stale(self, *, instance_profile_id: UUID) -> int:
        del instance_profile_id
        return 0

    def finish_scan(
        self,
        *,
        scan_run_id: UUID,
        succeeded: bool,
        fingerprint: str | None,
        error_code: str | None,
    ) -> None:
        del scan_run_id, error_code
        self.finished = (succeeded, fingerprint)

    def record_capability(
        self, *, instance_profile_id: UUID, state: SourceCapabilityState
    ) -> None:
        del instance_profile_id, state


class PartiallyFailingExtractor:
    def extract(self, context) -> FileExtraction:
        if context.logical_path.endswith("bad.py"):
            raise SourceExtractionError("python_parse_error")
        return FileExtraction()


def test_isolated_parser_error_preserves_valid_index_and_does_not_delete_stale(
    tmp_path: Path,
) -> None:
    root = tmp_path / "addons"
    module = root / "fixture"
    models = module / "models"
    models.mkdir(parents=True)
    (module / "__manifest__.py").write_text("{'name': 'Fixture'}\n", encoding="utf-8")
    (models / "good.py").write_text("VALUE = 1\n", encoding="utf-8")
    (models / "bad.py").write_text("VALUE = (\n", encoding="utf-8")

    store = Store()
    extractor = PartiallyFailingExtractor()
    scanner = SourceScanner(
        store=store,
        extractors={
            SourceFileKind.MANIFEST: extractor,
            SourceFileKind.PYTHON: extractor,
        },
        limits=ScanLimits(max_modules=10, max_files=20, max_total_bytes=100_000),
    )

    result = scanner.run(
        instance_profile_id=uuid4(),
        roots=RootSelection(override=(root,)),
        installed_modules=("fixture",),
    )

    assert result.capability is SourceCapabilityState.DETECTED
    assert any(error.code == "python_parse_error" for error in result.errors)
    assert any(error.code == "partial_scan" for error in result.errors)
    assert ("fixture", "fixture/models/good.py") in store.files
    assert ("fixture", "fixture/models/bad.py") not in store.files
    assert store.mark_stale_calls == 0
    assert store.finished is not None and store.finished[0] is True

"""SQLAlchemy-backed adapter for the source scan store port."""

from collections.abc import Mapping
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.orm import Session

from odoo_ai.contracts import SourceCapabilityState, SourceFileKind, SourceProvenance
from odoo_ai.source.scanner import (
    ExtractedSymbol,
    ExtractedXmlRecord,
    StoredSourceFile,
)
from odoo_ai.storage.runtime_repository import record_source_capability
from odoo_ai.storage.source_repository import (
    SourceSymbolValues,
    XmlRecordValues,
    finish_scan,
    mark_stale_source_files,
    open_scan,
    replace_file_derivatives,
    upsert_source_file,
)


class SqlAlchemySourceScanStore:
    """Map orchestrator operations to the small M3-02 repository surface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def open_scan(self, *, instance_profile_id: UUID) -> UUID:
        return open_scan(self._session, instance_profile_id=instance_profile_id).id

    def upsert_file(
        self,
        *,
        scan_run_id: UUID,
        module: str,
        logical_path: str,
        kind: SourceFileKind,
        fingerprint: str,
        size_bytes: int,
        provenance: SourceProvenance,
    ) -> StoredSourceFile:
        result = upsert_source_file(
            self._session,
            scan_run_id=scan_run_id,
            module=module,
            logical_path=logical_path,
            kind=kind.value,
            fingerprint=fingerprint,
            size_bytes=size_bytes,
            provenance=provenance.value,
        )
        return StoredSourceFile(
            file_id=result.file.id,
            fingerprint_changed=result.fingerprint_changed,
        )

    def replace_derivatives(
        self,
        *,
        source_file_id: UUID,
        symbols: tuple[ExtractedSymbol, ...],
        xml_records: tuple[ExtractedXmlRecord, ...],
        metadata: Mapping[str, JsonValue] | None,
    ) -> None:
        replace_file_derivatives(
            self._session,
            source_file_id=source_file_id,
            symbols=[
                SourceSymbolValues(
                    kind=value.kind,
                    model=value.model,
                    name=value.name,
                    start_line=value.start_line,
                    end_line=value.end_line,
                )
                for value in symbols
            ],
            xml_records=[
                XmlRecordValues(
                    xml_id=value.xml_id,
                    model=value.model,
                    start_line=value.start_line,
                    end_line=value.end_line,
                )
                for value in xml_records
            ],
            extracted_metadata=metadata,
        )

    def mark_stale(self, *, scan_run_id: UUID, seen_file_ids: set[UUID]) -> int:
        return mark_stale_source_files(
            self._session,
            scan_run_id=scan_run_id,
            seen_file_ids=seen_file_ids,
        )

    def finish_scan(
        self,
        *,
        scan_run_id: UUID,
        succeeded: bool,
        fingerprint: str | None,
        error_code: str | None,
    ) -> None:
        finish_scan(
            self._session,
            scan_run_id=scan_run_id,
            status="succeeded" if succeeded else "failed",
            fingerprint=fingerprint,
            error_code=error_code,
        )

    def record_capability(
        self, *, instance_profile_id: UUID, state: SourceCapabilityState
    ) -> None:
        record_source_capability(
            self._session,
            instance_profile_id=instance_profile_id,
            state=state,
        )

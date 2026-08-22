"""Small SQLAlchemy repository surface for the incremental source index."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from odoo_ai.storage.models import ScanRun, SourceFile, SourceSymbol, XmlRecord

type TerminalScanStatus = Literal["succeeded", "failed"]


@dataclass(frozen=True, slots=True)
class SourceSymbolValues:
    """Normalized symbol values produced by a later static extractor."""

    kind: str
    model: str | None
    name: str
    start_line: int
    end_line: int
    details: Mapping[str, JsonValue] | None = None


@dataclass(frozen=True, slots=True)
class XmlRecordValues:
    """Normalized XML values produced by a later static extractor."""

    xml_id: str
    model: str | None
    start_line: int | None = None
    end_line: int | None = None
    declaration: Mapping[str, JsonValue] | None = None


@dataclass(frozen=True, slots=True)
class SourceFileUpsert:
    """Upsert result distinguishing unchanged and changed fingerprints."""

    file: SourceFile
    fingerprint_changed: bool


@dataclass(frozen=True, slots=True)
class IndexedSourceSymbol:
    symbol_id: UUID
    source_file_id: UUID
    module: str
    kind: str
    model: str | None
    name: str
    logical_path: str
    start_line: int
    end_line: int
    fingerprint: str
    provenance: str
    observed_at: datetime
    details: dict[str, JsonValue] | None


@dataclass(frozen=True, slots=True)
class IndexedSourcePointer:
    source_file_id: UUID
    module: str
    logical_path: str
    kind: str
    fingerprint: str
    size_bytes: int
    provenance: str
    observed_at: datetime


def open_scan(session: Session, *, instance_profile_id: UUID) -> ScanRun:
    scan = ScanRun(instance_profile_id=instance_profile_id, status="running")
    session.add(scan)
    session.flush()
    return scan


def finish_scan(
    session: Session,
    *,
    scan_run_id: UUID,
    status: TerminalScanStatus,
    fingerprint: str | None = None,
    error_code: str | None = None,
) -> ScanRun:
    scan = session.get(ScanRun, scan_run_id)
    if scan is None:
        raise ValueError("unknown scan run")
    if scan.status != "running":
        raise ValueError("scan run is already finished")
    if status == "succeeded" and error_code is not None:
        raise ValueError("successful scan cannot have an error code")
    scan.status = status
    scan.completed_at = datetime.now(UTC)
    scan.fingerprint = fingerprint
    scan.error_code = error_code
    session.flush()
    return scan


def upsert_source_file(
    session: Session,
    *,
    scan_run_id: UUID,
    module: str,
    logical_path: str,
    kind: str,
    fingerprint: str,
    size_bytes: int,
    provenance: str = "unknown",
) -> SourceFileUpsert:
    scan = session.get(ScanRun, scan_run_id)
    if scan is None or scan.status != "running":
        raise ValueError("source files require an active scan run")

    source_file = session.scalar(
        select(SourceFile).where(
            SourceFile.instance_profile_id == scan.instance_profile_id,
            SourceFile.module == module,
            SourceFile.logical_path == logical_path,
        )
    )
    if source_file is None:
        source_file = SourceFile(
            instance_profile_id=scan.instance_profile_id,
            scan_run_id=scan.id,
            module=module,
            logical_path=logical_path,
            kind=kind,
            fingerprint=fingerprint,
            size_bytes=size_bytes,
            provenance=provenance,
            is_stale=False,
        )
        session.add(source_file)
        changed = True
    else:
        changed = source_file.fingerprint != fingerprint
        source_file.scan_run_id = scan.id
        source_file.kind = kind
        source_file.fingerprint = fingerprint
        source_file.size_bytes = size_bytes
        source_file.provenance = provenance
        source_file.is_stale = False
        if changed:
            source_file.extracted_metadata = None
    session.flush()
    return SourceFileUpsert(file=source_file, fingerprint_changed=changed)


def find_unchanged_source_file_id(
    session: Session,
    *,
    instance_profile_id: UUID,
    module: str,
    logical_path: str,
    fingerprint: str,
) -> UUID | None:
    return session.scalar(
        select(SourceFile.id).where(
            SourceFile.instance_profile_id == instance_profile_id,
            SourceFile.module == module,
            SourceFile.logical_path == logical_path,
            SourceFile.fingerprint == fingerprint,
            SourceFile.is_stale.is_(False),
        )
    )


def replace_file_derivatives(
    session: Session,
    *,
    source_file_id: UUID,
    symbols: list[SourceSymbolValues],
    xml_records: list[XmlRecordValues],
    extracted_metadata: Mapping[str, JsonValue] | None = None,
) -> tuple[list[SourceSymbol], list[XmlRecord]]:
    source_file = session.get(SourceFile, source_file_id)
    if source_file is None or source_file.is_stale:
        raise ValueError("source file is unavailable")

    session.execute(delete(SourceSymbol).where(SourceSymbol.source_file_id == source_file.id))
    session.execute(delete(XmlRecord).where(XmlRecord.source_file_id == source_file.id))
    source_file.extracted_metadata = (
        dict(extracted_metadata) if extracted_metadata is not None else None
    )

    created_symbols = [
        SourceSymbol(
            source_file_id=source_file.id,
            module=source_file.module,
            kind=value.kind,
            model=value.model,
            name=value.name,
            logical_path=source_file.logical_path,
            start_line=value.start_line,
            end_line=value.end_line,
            fingerprint=source_file.fingerprint,
            details=dict(value.details) if value.details is not None else None,
        )
        for value in symbols
    ]
    created_xml_records = [
        XmlRecord(
            source_file_id=source_file.id,
            module=source_file.module,
            xml_id=value.xml_id,
            model=value.model,
            logical_path=source_file.logical_path,
            start_line=value.start_line,
            end_line=value.end_line,
            fingerprint=source_file.fingerprint,
            declaration=(
                dict(value.declaration) if value.declaration is not None else None
            ),
        )
        for value in xml_records
    ]
    session.add_all([*created_symbols, *created_xml_records])
    session.flush()
    return created_symbols, created_xml_records


def mark_stale_source_files(
    session: Session, *, scan_run_id: UUID, seen_file_ids: set[UUID]
) -> int:
    scan = session.get(ScanRun, scan_run_id)
    if scan is None or scan.status != "running":
        raise ValueError("stale cleanup requires an active scan run")

    filters = [
        SourceFile.instance_profile_id == scan.instance_profile_id,
        SourceFile.is_stale.is_(False),
    ]
    if seen_file_ids:
        filters.append(SourceFile.id.not_in(seen_file_ids))
    result = session.connection().execute(
        update(SourceFile).where(*filters).values(is_stale=True)
    )
    session.flush()
    return result.rowcount


def delete_stale_source_files(session: Session, *, instance_profile_id: UUID) -> int:
    result = session.connection().execute(
        delete(SourceFile).where(
            SourceFile.instance_profile_id == instance_profile_id,
            SourceFile.is_stale.is_(True),
        )
    )
    session.flush()
    return result.rowcount


def find_source_symbols(
    session: Session,
    *,
    instance_profile_id: UUID,
    model: str | None = None,
    name: str | None = None,
    module: str | None = None,
    logical_path: str | None = None,
    limit: int = 50,
) -> list[SourceSymbol]:
    if not any((model, name, module, logical_path)):
        raise ValueError("at least one structural symbol identifier is required")
    if not 1 <= limit <= 200:
        raise ValueError("symbol query limit must be between 1 and 200")
    statement = (
        select(SourceSymbol)
        .join(SourceFile, SourceFile.id == SourceSymbol.source_file_id)
        .where(
            SourceFile.instance_profile_id == instance_profile_id,
            SourceFile.is_stale.is_(False),
            SourceSymbol.fingerprint == SourceFile.fingerprint,
        )
    )
    for column, value in (
        (SourceSymbol.model, model),
        (SourceSymbol.name, name),
        (SourceSymbol.module, module),
        (SourceSymbol.logical_path, logical_path),
    ):
        if value is not None:
            statement = statement.where(column == value)
    return list(session.scalars(statement.order_by(SourceSymbol.id).limit(limit)))


def find_xml_records(
    session: Session,
    *,
    instance_profile_id: UUID,
    xml_id: str | None = None,
    model: str | None = None,
    limit: int = 50,
) -> list[XmlRecord]:
    if xml_id is None and model is None:
        raise ValueError("xml_id or model is required")
    if not 1 <= limit <= 200:
        raise ValueError("XML query limit must be between 1 and 200")
    statement = (
        select(XmlRecord)
        .join(SourceFile, SourceFile.id == XmlRecord.source_file_id)
        .where(
            SourceFile.instance_profile_id == instance_profile_id,
            SourceFile.is_stale.is_(False),
            XmlRecord.fingerprint == SourceFile.fingerprint,
        )
    )
    if xml_id is not None:
        statement = statement.where(XmlRecord.xml_id == xml_id)
    if model is not None:
        statement = statement.where(XmlRecord.model == model)
    return list(session.scalars(statement.order_by(XmlRecord.id).limit(limit)))


def search_indexed_source_symbols(
    session: Session,
    *,
    instance_profile_id: UUID,
    query: str,
    normalized_query: str,
    model: str | None = None,
    module: str | None = None,
    limit: int = 200,
) -> list[IndexedSourceSymbol]:
    if not query or not normalized_query:
        raise ValueError("bounded source query is required")
    if not 1 <= limit <= 200:
        raise ValueError("source candidate pool must be between 1 and 200")
    normalized_name = func.regexp_replace(
        func.lower(SourceSymbol.name), "[^a-z0-9]+", "", "g"
    )
    statement = (
        select(SourceSymbol, SourceFile.provenance, ScanRun.completed_at)
        .join(SourceFile, SourceFile.id == SourceSymbol.source_file_id)
        .join(ScanRun, ScanRun.id == SourceFile.scan_run_id)
        .where(
            SourceFile.instance_profile_id == instance_profile_id,
            SourceFile.is_stale.is_(False),
            SourceSymbol.fingerprint == SourceFile.fingerprint,
            ScanRun.status == "succeeded",
            or_(
                SourceSymbol.name == query,
                func.lower(SourceSymbol.name) == query.casefold(),
                normalized_name == normalized_query,
                normalized_name.endswith(normalized_query),
            ),
        )
    )
    if model is not None:
        statement = statement.where(SourceSymbol.model == model)
    if module is not None:
        statement = statement.where(SourceSymbol.module == module)
    rows = session.execute(statement.order_by(SourceSymbol.id).limit(limit))
    return [
        _indexed_symbol(symbol, provenance, completed_at)
        for symbol, provenance, completed_at in rows
        if completed_at is not None
    ]


def find_indexed_model_extensions(
    session: Session,
    *,
    instance_profile_id: UUID,
    model: str,
    module: str | None = None,
    limit: int = 50,
) -> list[IndexedSourceSymbol]:
    if not model:
        raise ValueError("model is required")
    if not 1 <= limit <= 50:
        raise ValueError("model extension limit must be between 1 and 50")
    statement = (
        select(SourceSymbol, SourceFile.provenance, ScanRun.completed_at)
        .join(SourceFile, SourceFile.id == SourceSymbol.source_file_id)
        .join(ScanRun, ScanRun.id == SourceFile.scan_run_id)
        .where(
            SourceFile.instance_profile_id == instance_profile_id,
            SourceFile.is_stale.is_(False),
            SourceSymbol.fingerprint == SourceFile.fingerprint,
            SourceSymbol.kind.in_(("model", "inherit")),
            SourceSymbol.model == model,
            ScanRun.status == "succeeded",
        )
    )
    if module is not None:
        statement = statement.where(SourceSymbol.module == module)
    rows = session.execute(
        statement.order_by(SourceSymbol.module, SourceSymbol.logical_path, SourceSymbol.id).limit(
            limit
        )
    )
    return [
        _indexed_symbol(symbol, provenance, completed_at)
        for symbol, provenance, completed_at in rows
        if completed_at is not None
    ]


def get_indexed_source_pointer(
    session: Session,
    *,
    instance_profile_id: UUID,
    source_file_id: UUID,
    fingerprint: str,
    start_line: int,
    end_line: int,
) -> IndexedSourcePointer | None:
    row = session.execute(
        select(SourceFile, ScanRun.completed_at)
        .join(ScanRun, ScanRun.id == SourceFile.scan_run_id)
        .where(
            SourceFile.id == source_file_id,
            SourceFile.instance_profile_id == instance_profile_id,
            SourceFile.fingerprint == fingerprint,
            SourceFile.is_stale.is_(False),
            ScanRun.status == "succeeded",
        )
    ).one_or_none()
    if row is None:
        return None
    source_file, completed_at = row
    if completed_at is None:
        return None
    symbol_id = session.scalar(
        select(SourceSymbol.id)
        .where(
            SourceSymbol.source_file_id == source_file_id,
            SourceSymbol.fingerprint == fingerprint,
            SourceSymbol.start_line == start_line,
            SourceSymbol.end_line == end_line,
        )
        .limit(1)
    )
    if symbol_id is None:
        xml_record_id = session.scalar(
            select(XmlRecord.id)
            .where(
                XmlRecord.source_file_id == source_file_id,
                XmlRecord.fingerprint == fingerprint,
                XmlRecord.start_line == start_line,
                XmlRecord.end_line == end_line,
            )
            .limit(1)
        )
        if xml_record_id is None:
            return None
    return IndexedSourcePointer(
        source_file_id=source_file.id,
        module=source_file.module,
        logical_path=source_file.logical_path,
        kind=source_file.kind,
        fingerprint=source_file.fingerprint,
        size_bytes=source_file.size_bytes,
        provenance=source_file.provenance,
        observed_at=completed_at,
    )


def _indexed_symbol(
    symbol: SourceSymbol, provenance: str, observed_at: datetime
) -> IndexedSourceSymbol:
    return IndexedSourceSymbol(
        symbol_id=symbol.id,
        source_file_id=symbol.source_file_id,
        module=symbol.module,
        kind=symbol.kind,
        model=symbol.model,
        name=symbol.name,
        logical_path=symbol.logical_path,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        fingerprint=symbol.fingerprint,
        provenance=provenance,
        observed_at=observed_at,
        details=symbol.details,
    )

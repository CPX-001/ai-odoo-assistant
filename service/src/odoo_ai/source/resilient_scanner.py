"""Production scanner policy that preserves useful index data on isolated source errors."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from uuid import UUID

from odoo_ai.contracts import SourceCapabilityState, SourceProvenance
from odoo_ai.source.scanner import (
    FileScanContext,
    RootSelection,
    ScanError,
    SourceExtractionError,
    SourceScanMetrics,
    SourceScanResult,
    _check_time,
    _failed_root_state,
    _iter_module_files,
    _PreparedFile,
    _ScanLimitError,
    locate_installed_modules,
    resolve_source_roots,
)
from odoo_ai.source.scanner import SourceScanner as _BaseSourceScanner


class ResilientSourceScanner(_BaseSourceScanner):
    """Keep a usable persistent index when individual files cannot be scanned.

    Global safety limits still fail the run. Isolated file/directory/parser errors are
    reported as a partial scan, valid files are persisted, and previously indexed unseen
    files are retained until a complete scan can prove that they became stale.
    """

    def run(
        self,
        *,
        instance_profile_id: UUID,
        roots: RootSelection,
        installed_modules: Iterable[str],
        provenance: Mapping[str, SourceProvenance] | None = None,
    ) -> SourceScanResult:
        resolution = resolve_source_roots(roots, probe=self._root_probe)
        root_errors = tuple(ScanError(issue.code) for issue in resolution.issues)
        if not resolution.roots:
            state = _failed_root_state(resolution.issues)
            self._store.record_capability(instance_profile_id=instance_profile_id, state=state)
            return SourceScanResult(state, None, None, SourceScanMetrics(), root_errors)

        installed = tuple(dict.fromkeys(installed_modules))
        inventory = locate_installed_modules(
            resolution.roots,
            installed,
            max_modules=self._limits.max_modules,
            provenance=provenance,
        )
        initial_errors = (*root_errors, *inventory.issues)
        if not inventory.modules and installed:
            state = (
                SourceCapabilityState.ERROR
                if any(error.code == "module_limit_exceeded" for error in inventory.issues)
                else SourceCapabilityState.NOT_FOUND
            )
            self._store.record_capability(instance_profile_id=instance_profile_id, state=state)
            return SourceScanResult(state, None, None, SourceScanMetrics(), initial_errors)

        scan_id = self._store.open_scan(instance_profile_id=instance_profile_id)
        started = self._clock()
        prepared_files: list[_PreparedFile] = []
        aggregate_items: list[str] = []
        errors = list(initial_errors)
        files_seen = files_extracted = files_unchanged = bytes_hashed = 0
        stale_files = 0
        try:
            for module in inventory.modules:
                for physical_path, logical_path, kind in _iter_module_files(
                    module, self._limits, errors
                ):
                    _check_time(started, self._clock(), self._limits.max_seconds)
                    if files_seen >= self._limits.max_files:
                        raise _ScanLimitError("file_limit_exceeded")
                    files_seen += 1
                    try:
                        metadata = physical_path.stat()
                        if metadata.st_size > self._limits.max_file_bytes:
                            errors.append(ScanError("file_too_large", module.name, logical_path))
                            continue
                        content = physical_path.read_bytes()
                        if len(content) != metadata.st_size:
                            metadata = physical_path.stat()
                        if len(content) > self._limits.max_file_bytes:
                            errors.append(ScanError("file_too_large", module.name, logical_path))
                            continue
                        if bytes_hashed + len(content) > self._limits.max_total_bytes:
                            raise _ScanLimitError("byte_limit_exceeded")
                    except PermissionError:
                        errors.append(ScanError("file_no_permission", module.name, logical_path))
                        continue
                    except OSError:
                        errors.append(ScanError("file_read_error", module.name, logical_path))
                        continue

                    digest = "sha256:" + hashlib.sha256(content).hexdigest()
                    bytes_hashed += len(content)
                    aggregate_items.append(f"{module.name}\0{logical_path}\0{digest}")
                    unchanged_id = self._store.find_unchanged_file(
                        instance_profile_id=instance_profile_id,
                        module=module.name,
                        logical_path=logical_path,
                        fingerprint=digest,
                    )
                    if unchanged_id is not None:
                        files_unchanged += 1
                        prepared_files.append(
                            _PreparedFile(module, logical_path, kind, digest, len(content), None)
                        )
                        continue

                    extractor = self._extractors.get(kind)
                    if extractor is None:
                        errors.append(ScanError("extractor_unavailable", module.name, logical_path))
                        continue
                    try:
                        extraction = extractor.extract(
                            FileScanContext(
                                module=module.name,
                                logical_path=logical_path,
                                kind=kind,
                                fingerprint=digest,
                                size_bytes=len(content),
                                mtime_ns=metadata.st_mtime_ns,
                                content=content,
                            )
                        )
                        prepared_files.append(
                            _PreparedFile(
                                module,
                                logical_path,
                                kind,
                                digest,
                                len(content),
                                extraction,
                            )
                        )
                        files_extracted += 1
                    except SourceExtractionError as error:
                        errors.append(ScanError(error.code, module.name, logical_path))
                    except Exception:  # noqa: BLE001 - isolate one extractor/file
                        errors.append(ScanError("extractor_error", module.name, logical_path))

            aggregate = "\n".join(sorted(aggregate_items)).encode("utf-8")
            fingerprint = "sha256:" + hashlib.sha256(aggregate).hexdigest()
            partial = bool(errors)
            if partial and not any(error.code == "partial_scan" for error in errors):
                errors.append(ScanError("partial_scan"))

            seen_ids: set[UUID] = set()
            for prepared in prepared_files:
                stored = self._store.upsert_file(
                    scan_run_id=scan_id,
                    module=prepared.module.name,
                    logical_path=prepared.logical_path,
                    kind=prepared.kind,
                    fingerprint=prepared.fingerprint,
                    size_bytes=prepared.size_bytes,
                    provenance=prepared.module.provenance,
                )
                seen_ids.add(stored.file_id)
                if prepared.extraction is not None:
                    self._store.replace_derivatives(
                        source_file_id=stored.file_id,
                        symbols=prepared.extraction.symbols,
                        xml_records=prepared.extraction.xml_records,
                        metadata=prepared.extraction.metadata,
                    )

            # Never delete old index rows after an incomplete traversal: an unreadable
            # directory/file is not evidence that the previously indexed file disappeared.
            if not partial:
                stale_files = self._store.mark_stale(
                    scan_run_id=scan_id,
                    seen_file_ids=seen_ids,
                )
                self._store.delete_stale(instance_profile_id=instance_profile_id)

            self._store.finish_scan(
                scan_run_id=scan_id,
                succeeded=True,
                fingerprint=fingerprint,
                error_code=None,
            )
            state = SourceCapabilityState.DETECTED
        except _ScanLimitError as error:
            errors.append(ScanError(str(error)))
            self._store.finish_scan(
                scan_run_id=scan_id,
                succeeded=False,
                fingerprint=None,
                error_code=str(error),
            )
            fingerprint = None
            state = SourceCapabilityState.ERROR

        self._store.record_capability(instance_profile_id=instance_profile_id, state=state)
        return SourceScanResult(
            capability=state,
            scan_run_id=scan_id,
            fingerprint=fingerprint,
            metrics=SourceScanMetrics(
                modules=len(inventory.modules),
                files_seen=files_seen,
                files_extracted=files_extracted,
                files_unchanged=files_unchanged,
                bytes_hashed=bytes_hashed,
                stale_files=stale_files,
            ),
            errors=tuple(errors),
        )

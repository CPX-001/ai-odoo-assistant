"""Bounded source/XML Evidence for installed Odoo addons.

The model never supplies a filesystem root.  Trusted host code resolves installed
module names to their effective addon roots, while Evidence locators retain only a
module name, a relative path and a bounded line range.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from .contracts import CapabilityContext, CapabilityError, JsonValue
from .evidence import (
    EvidenceAccessScope,
    EvidenceFreshness,
    EvidenceItem,
    EvidenceKind,
    EvidenceLocator,
    EvidenceProvider,
    EvidenceRef,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    EvidenceTrust,
)

PROVIDER_ID = "assistant.installed_source"
SOURCE_ID = "odoo.installed_addons"
MAX_FILES = 512
MAX_SCAN_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
MAX_SCAN_SECONDS = 2.0
MAX_MATCHES = 12
_ALLOWED_SUFFIXES = frozenset({".py", ".xml", ".csv", ".md", ".rst"})
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_.-]{2,}")
_IGNORED_PARTS = frozenset(
    {".git", "__pycache__", "node_modules", "filestore", "secrets", "codex_home"}
)

RootResolver = Callable[[CapabilityContext], Mapping[str, Path]]


def _is_technical(context: CapabilityContext) -> bool:
    user = getattr(getattr(context, "env", None), "user", None)
    try:
        return bool(user and user.has_group("base.group_system"))
    except Exception:  # noqa: BLE001 - technical Evidence fails closed
        return False


def _odoo_module_roots(context: CapabilityContext) -> Mapping[str, Path]:
    env = getattr(context, "env", None)
    if env is None:
        raise CapabilityError("source_evidence_env_unavailable")
    try:
        from odoo.modules.module import get_module_path

        installed = env["ir.module.module"]._installed()
    except Exception as exc:
        raise CapabilityError("source_evidence_modules_unavailable") from exc
    if not isinstance(installed, dict):
        raise CapabilityError("source_evidence_modules_invalid")
    roots: dict[str, Path] = {}
    for module in sorted(str(name) for name in installed if name)[:256]:
        try:
            raw_path = get_module_path(module, display_warning=False)
            path = Path(raw_path).resolve(strict=True) if raw_path else None
        except (OSError, RuntimeError, TypeError, ValueError):
            continue
        if path is not None and path.is_dir():
            roots[module] = path
    return roots


def _query_terms(query: str) -> tuple[str, ...]:
    ignored = {
        "about",
        "como",
        "cómo",
        "donde",
        "error",
        "esta",
        "este",
        "funciona",
        "hace",
        "odoo",
        "para",
        "porque",
        "source",
        "the",
        "this",
    }
    return tuple(
        dict.fromkeys(
            token.casefold()
            for token in _TOKEN_RE.findall(query)
            if token.casefold() not in ignored
        )
    )[:12]


def _safe_source_path(root: Path, logical_path: str) -> Path:
    if not logical_path or logical_path.startswith(("/", "\\")):
        raise CapabilityError("source_evidence_locator_invalid")
    candidate = (root / logical_path).resolve(strict=True)
    try:
        candidate.relative_to(root.resolve(strict=True))
    except ValueError:
        raise CapabilityError("source_evidence_path_escape") from None
    if candidate.is_symlink() or not candidate.is_file():
        raise CapabilityError("source_evidence_file_invalid")
    if candidate.suffix.casefold() not in _ALLOWED_SUFFIXES:
        raise CapabilityError("source_evidence_file_type_invalid")
    return candidate


def _read_bounded(path: Path) -> str:
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise CapabilityError("source_evidence_file_too_large")
        return path.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        raise CapabilityError("source_evidence_access_denied") from None
    except FileNotFoundError:
        raise CapabilityError("source_evidence_missing") from None
    except OSError:
        raise CapabilityError("source_evidence_read_failed") from None


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line_window(lines: list[str], matched: list[int]) -> tuple[int, int]:
    start = max(0, min(matched) - 3)
    end = min(len(lines), max(matched) + 4)
    if end - start > 120:
        end = start + 120
    return start + 1, end


def _make_ref(
    context: CapabilityContext,
    *,
    module: str,
    logical_path: str,
    line_start: int,
    line_end: int,
    fingerprint: str,
    kind: EvidenceKind,
    score: float,
    freshness: EvidenceFreshness = EvidenceFreshness.CURRENT,
) -> EvidenceRef:
    identity = hashlib.sha256(f"{module}:{logical_path}".encode()).hexdigest()[:24]
    return EvidenceRef(
        evidence_id=f"source:{identity}",
        kind=kind,
        provider_id=PROVIDER_ID,
        locator=EvidenceLocator(
            provider_id=PROVIDER_ID,
            source_id=SOURCE_ID,
            key=f"{module}/{logical_path}",
            parameters={"line_start": line_start, "line_end": line_end},
        ),
        title=f"{module}: {logical_path}",
        provenance=f"Installed Odoo addon {module}, logical path {logical_path}",
        fingerprint=fingerprint,
        captured_at=datetime.now(UTC),
        freshness=freshness,
        trust=EvidenceTrust.VERIFIED_SOURCE,
        access_scope=EvidenceAccessScope.bind(
            context, group_xmlids=("base.group_system",)
        ),
        citation={
            "source_type": "installed_addon_source",
            "module": module,
            "logical_path": logical_path,
            "line_start": line_start,
            "line_end": line_end,
        },
        score=score,
        metadata={"logical_locator_only": True, "technical_only": True},
    )


def build_installed_source_evidence_provider(
    *, root_resolver: RootResolver | None = None
) -> EvidenceProvider:
    resolve_roots = root_resolver or _odoo_module_roots

    def search(
        context: CapabilityContext, request: EvidenceSearchRequest
    ) -> EvidenceSearchResult:
        if request.kinds and not {EvidenceKind.SOURCE, EvidenceKind.XML}.intersection(
            request.kinds
        ):
            return EvidenceSearchResult(provider_id=PROVIDER_ID, refs=())
        terms = _query_terms(request.query)
        if not terms:
            return EvidenceSearchResult(provider_id=PROVIDER_ID, refs=())
        started = time.monotonic()
        scanned_files = 0
        scanned_bytes = 0
        ranked: list[tuple[float, EvidenceRef]] = []
        truncated = False
        roots = resolve_roots(context)
        roots_by_folded_name = {name.casefold(): (name, root) for name, root in roots.items()}
        explicitly_named = [
            roots_by_folded_name[term]
            for term in terms
            if term in roots_by_folded_name
        ]
        ordered_roots = sorted(
            explicitly_named or roots.items(),
            key=lambda item: (
                not any(term in item[0].casefold() for term in terms),
                item[0],
            ),
        )
        for module, root in ordered_roots:
            root = Path(root).resolve(strict=True)
            for directory, names, files in os.walk(root, followlinks=False):
                names[:] = sorted(
                    name
                    for name in names
                    if name.casefold() not in _IGNORED_PARTS
                    and not (Path(directory) / name).is_symlink()
                )
                for filename in sorted(files):
                    path = Path(directory) / filename
                    if path.suffix.casefold() not in _ALLOWED_SUFFIXES or path.is_symlink():
                        continue
                    scanned_files += 1
                    if scanned_files > MAX_FILES or time.monotonic() - started > MAX_SCAN_SECONDS:
                        truncated = True
                        break
                    logical = path.relative_to(root).as_posix()
                    try:
                        size = path.stat().st_size
                    except OSError:
                        continue
                    scanned_bytes += min(size, MAX_FILE_BYTES)
                    if scanned_bytes > MAX_SCAN_BYTES:
                        truncated = True
                        break
                    if size > MAX_FILE_BYTES:
                        continue
                    text = _read_bounded(path)
                    folded = text.casefold()
                    path_folded = f"{module}/{logical}".casefold()
                    hits = [index for index, line in enumerate(text.splitlines()) if any(term in line.casefold() for term in terms)]
                    path_hits = sum(term in path_folded for term in terms)
                    if not hits and not path_hits:
                        continue
                    lines = text.splitlines()
                    line_start, line_end = _line_window(lines, hits or [0])
                    distinct_hits = sum(
                        term in folded or term in path_folded for term in terms
                    )
                    score = float(
                        distinct_hits * 100
                        + path_hits * 20
                        + sum(min(folded.count(term), 5) for term in terms)
                    )
                    kind = EvidenceKind.XML if path.suffix.casefold() == ".xml" else EvidenceKind.SOURCE
                    ranked.append(
                        (
                            score,
                            _make_ref(
                                context,
                                module=module,
                                logical_path=logical,
                                line_start=line_start,
                                line_end=line_end,
                                fingerprint=_fingerprint(text),
                                kind=kind,
                                score=score,
                            ),
                        )
                    )
                if truncated:
                    break
            if truncated:
                break
        refs = tuple(
            item[1]
            for item in sorted(ranked, key=lambda item: (-item[0], item[1].evidence_id))[
                : min(request.max_results, MAX_MATCHES)
            ]
        )
        return EvidenceSearchResult(provider_id=PROVIDER_ID, refs=refs, truncated=truncated)

    def fetch(context: CapabilityContext, requested: EvidenceRef) -> EvidenceItem:
        if not requested.access_scope.allows(context):
            raise CapabilityError("evidence_access_denied")
        try:
            module, logical_path = requested.locator.key.split("/", 1)
        except ValueError:
            raise CapabilityError("source_evidence_locator_invalid") from None
        root = resolve_roots(context).get(module)
        if root is None:
            raise CapabilityError("source_evidence_module_missing")
        path = _safe_source_path(Path(root), logical_path)
        text = _read_bounded(path)
        current_fingerprint = _fingerprint(text)
        freshness = (
            EvidenceFreshness.CURRENT
            if current_fingerprint == requested.fingerprint
            else EvidenceFreshness.STALE
        )
        line_start = int(requested.locator.parameters.get("line_start") or 1)
        line_end = int(requested.locator.parameters.get("line_end") or line_start)
        lines = text.splitlines()
        excerpt = "\n".join(lines[max(0, line_start - 1) : min(len(lines), line_end)])
        ref = _make_ref(
            context,
            module=module,
            logical_path=logical_path,
            line_start=line_start,
            line_end=line_end,
            fingerprint=current_fingerprint,
            kind=requested.kind,
            score=requested.score or 0.0,
            freshness=freshness,
        )
        data: dict[str, JsonValue] = {
            "module": module,
            "logical_path": logical_path,
            "line_start": line_start,
            "line_end": line_end,
        }
        if freshness is EvidenceFreshness.STALE:
            data["requested_fingerprint"] = requested.fingerprint
            data["current_fingerprint"] = current_fingerprint
        return EvidenceItem(ref=ref, excerpt=excerpt, data=data)

    return EvidenceProvider(
        provider_id=PROVIDER_ID,
        version="1",
        kinds=(EvidenceKind.SOURCE, EvidenceKind.XML),
        search=search,
        fetch=fetch,
        guard=_is_technical,
        optional=True,
        max_results=MAX_MATCHES,
        max_excerpt_bytes=8 * 1024,
        max_total_bytes=64 * 1024,
        metadata={
            "namespace_owner": "core",
            "logical_locator_only": True,
            "installed_modules_only": True,
            "technical_only": True,
        },
    )


__all__ = [
    "PROVIDER_ID",
    "SOURCE_ID",
    "build_installed_source_evidence_provider",
]

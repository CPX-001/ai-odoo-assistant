"""Provider-neutral, bounded evidence contracts.

Evidence is contextual data.  It is never executable authority and cannot alter
capability availability, policy, approval, identity or the effective technical
profile.  Providers return logical locators and bounded projections; the host
rechecks access and freshness when a reference is fetched.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, TypeAlias

from .contracts import CapabilityContext, CapabilityError, JsonValue

EVIDENCE_FORMAT_VERSION = 1
DEFAULT_MAX_RESULTS = 20
DEFAULT_MAX_EXCERPT_BYTES = 24 * 1024
DEFAULT_MAX_TOTAL_BYTES = 96 * 1024
LEDGER_MAX_REFS = 64
LEDGER_MAX_EXCERPTS = 16
LEDGER_MAX_EXCERPT_BYTES = 8 * 1024
LEDGER_MAX_TOTAL_BYTES = 64 * 1024
MAX_JSON_DEPTH = 12
MAX_JSON_KEYS = 256
MAX_JSON_ITEMS = 512
MAX_JSON_BYTES = 96 * 1024
REDACTED_SECRET = "[REDACTED_SECRET]"

_PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_EVIDENCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,191}$")
_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,159}$")
_GROUP_XMLID_RE = re.compile(r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_.-]+$")
_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|passwd|secret|private[_-]?key)",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
)


class EvidenceKind(StrEnum):
    RUNTIME = "runtime"
    SCHEMA = "schema"
    CONFIGURATION = "configuration"
    SOURCE = "source"
    XML = "xml"
    LOG = "log"
    DOCUMENT = "document"
    WEB = "web"
    BUSINESS_RECORD = "business_record"
    DIAGNOSTIC = "diagnostic"


class EvidenceTrust(StrEnum):
    HOST_FACT = "host_fact"
    VERIFIED_SOURCE = "verified_source"
    USER_CONTENT = "user_content"
    EXTERNAL_CONTENT = "external_content"
    UNTRUSTED = "untrusted"


class EvidenceFreshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"
    MISSING = "missing"
    REVOKED = "revoked"


def utcnow() -> datetime:
    return datetime.now(UTC)


def redact_secrets(value: str) -> str:
    """Redact common credentials without treating their presence as authority.

    This is deliberately a last-mile safety net, not the only secret control.
    Callers should avoid collecting sensitive fields in the first place.
    """

    text = value
    for pattern in _SECRET_VALUE_PATTERNS:
        text = pattern.sub(REDACTED_SECRET, text)
    return text


def freeze_json(value: Any, *, max_bytes: int = MAX_JSON_BYTES) -> JsonValue:
    """Validate, redact and deeply freeze a finite JSON-compatible value."""

    counter = {"keys": 0, "items": 0}
    frozen = _freeze_json(value, depth=0, counter=counter, secret_key=False)
    if len(canonical_json_bytes(frozen)) > max_bytes:
        raise CapabilityError("evidence_json_too_large")
    return frozen  # type: ignore[return-value]


def freeze_json_mapping(
    value: Mapping[str, Any] | None,
    *,
    max_bytes: int = MAX_JSON_BYTES,
) -> Mapping[str, JsonValue]:
    frozen = freeze_json(dict(value or {}), max_bytes=max_bytes)
    if not isinstance(frozen, Mapping):
        raise CapabilityError("evidence_mapping_invalid")
    return frozen


def thaw_json(value: Any) -> JsonValue:
    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        thaw_json(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _freeze_json(
    value: Any,
    *,
    depth: int,
    counter: dict[str, int],
    secret_key: bool,
) -> Any:
    if depth > MAX_JSON_DEPTH:
        raise CapabilityError("evidence_json_depth_exceeded")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CapabilityError("evidence_json_non_finite")
        return value
    if isinstance(value, str):
        text = REDACTED_SECRET if secret_key and value else redact_secrets(value)
        if len(text.encode("utf-8")) > DEFAULT_MAX_EXCERPT_BYTES:
            raise CapabilityError("evidence_string_too_large")
        return text
    if isinstance(value, Mapping):
        if len(value) > MAX_JSON_KEYS:
            raise CapabilityError("evidence_json_keys_exceeded")
        result: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str) or not key or len(key) > 160:
                raise CapabilityError("evidence_json_key_invalid")
            counter["keys"] += 1
            if counter["keys"] > MAX_JSON_KEYS:
                raise CapabilityError("evidence_json_keys_exceeded")
            result[key] = _freeze_json(
                value[key],
                depth=depth + 1,
                counter=counter,
                secret_key=bool(_SECRET_KEY_RE.search(key)),
            )
        return MappingProxyType(result)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > MAX_JSON_ITEMS:
            raise CapabilityError("evidence_json_items_exceeded")
        result = []
        for item in value:
            counter["items"] += 1
            if counter["items"] > MAX_JSON_ITEMS:
                raise CapabilityError("evidence_json_items_exceeded")
            result.append(
                _freeze_json(
                    item,
                    depth=depth + 1,
                    counter=counter,
                    secret_key=False,
                )
            )
        return tuple(result)
    raise CapabilityError("evidence_json_type_invalid")


def _bounded_text(value: str, *, limit: int, code: str) -> str:
    if not isinstance(value, str):
        raise CapabilityError(code)
    text = redact_secrets(value.strip())
    if len(text.encode("utf-8")) > limit:
        raise CapabilityError(code)
    return text


def _context_user_id(context: CapabilityContext) -> int | None:
    for candidate in (
        getattr(context, "user_id", None),
        getattr(getattr(context, "env", None), "uid", None),
        getattr(getattr(context, "user", None), "id", None),
    ):
        if isinstance(candidate, int) and candidate > 0:
            return candidate
    return None


def _context_company_ids(context: CapabilityContext) -> tuple[int, ...]:
    explicit = getattr(context, "company_ids", None)
    if explicit:
        return tuple(sorted({int(item) for item in explicit if int(item) > 0}))
    env = getattr(context, "env", None)
    companies = getattr(env, "companies", None)
    ids = getattr(companies, "ids", ())
    return tuple(sorted({int(item) for item in ids if int(item) > 0}))


def _context_group_xmlids(context: CapabilityContext) -> tuple[str, ...]:
    explicit = getattr(context, "group_xmlids", None)
    if explicit:
        return tuple(sorted({str(item) for item in explicit if item}))
    return ()


@dataclass(frozen=True, slots=True)
class EvidenceAccessScope:
    """Identity binding that is checked both at collection and fetch time."""

    user_id: int | None = None
    company_ids: tuple[int, ...] = ()
    group_xmlids: tuple[str, ...] = ()
    source_acl: tuple[str, ...] = ()
    public: bool = False

    def __post_init__(self) -> None:
        if self.user_id is not None and (not isinstance(self.user_id, int) or self.user_id <= 0):
            raise CapabilityError("evidence_scope_user_invalid")
        companies = tuple(sorted({int(item) for item in self.company_ids}))
        if any(item <= 0 for item in companies):
            raise CapabilityError("evidence_scope_company_invalid")
        groups = tuple(sorted({str(item) for item in self.group_xmlids}))
        if any(not _GROUP_XMLID_RE.fullmatch(item) for item in groups):
            raise CapabilityError("evidence_scope_group_invalid")
        source_acl = tuple(sorted({str(item) for item in self.source_acl if item}))
        if any(len(item) > 160 for item in source_acl):
            raise CapabilityError("evidence_scope_source_acl_invalid")
        object.__setattr__(self, "company_ids", companies)
        object.__setattr__(self, "group_xmlids", groups)
        object.__setattr__(self, "source_acl", source_acl)

    @classmethod
    def bind(
        cls,
        context: CapabilityContext,
        *,
        group_xmlids: Iterable[str] = (),
        source_acl: Iterable[str] = (),
    ) -> "EvidenceAccessScope":
        return cls(
            user_id=_context_user_id(context),
            company_ids=_context_company_ids(context),
            group_xmlids=tuple(group_xmlids),
            source_acl=tuple(source_acl),
        )

    def allows(
        self,
        context: CapabilityContext,
        *,
        source_acl: Iterable[str] = (),
    ) -> bool:
        if not self.public:
            if self.user_id is not None and self.user_id != _context_user_id(context):
                return False
            current_companies = set(_context_company_ids(context))
            if self.company_ids and not set(self.company_ids).issubset(current_companies):
                return False
            current_groups = set(_context_group_xmlids(context))
            if self.group_xmlids and not set(self.group_xmlids).issubset(current_groups):
                env_user = getattr(getattr(context, "env", None), "user", None)
                if env_user is None:
                    return False
                try:
                    if not all(env_user.has_group(item) for item in self.group_xmlids):
                        return False
                except Exception:
                    return False
        requested_acl = set(source_acl)
        return not self.source_acl or set(self.source_acl).issubset(requested_acl)

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "user_id": self.user_id,
            "company_ids": list(self.company_ids),
            "group_xmlids": list(self.group_xmlids),
            "source_acl": list(self.source_acl),
            "public": self.public,
        }


@dataclass(frozen=True, slots=True)
class EvidenceLocator:
    """Host-created logical locator.  It is not a filesystem path or command."""

    provider_id: str
    source_id: str
    key: str
    parameters: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("evidence_provider_id_invalid")
        if not _SOURCE_ID_RE.fullmatch(self.source_id):
            raise CapabilityError("evidence_source_id_invalid")
        key = _bounded_text(self.key, limit=512, code="evidence_locator_invalid")
        if not key or key.startswith(("/", "\\")) or ".." in key.split("/") or "\x00" in key:
            raise CapabilityError("evidence_locator_invalid")
        object.__setattr__(self, "key", key)
        object.__setattr__(
            self,
            "parameters",
            freeze_json_mapping(self.parameters, max_bytes=8 * 1024),
        )

    @property
    def canonical_key(self) -> str:
        digest = canonical_fingerprint(self.parameters)[:16]
        return f"{self.provider_id}:{self.source_id}:{self.key}:{digest}"

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "provider_id": self.provider_id,
            "source_id": self.source_id,
            "key": self.key,
            "parameters": thaw_json(self.parameters),
        }


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: str
    kind: EvidenceKind
    provider_id: str
    locator: EvidenceLocator
    title: str
    provenance: str
    fingerprint: str
    captured_at: datetime
    freshness: EvidenceFreshness
    trust: EvidenceTrust
    access_scope: EvidenceAccessScope
    citation: Mapping[str, JsonValue] = field(default_factory=dict)
    conflict_group: str = ""
    score: float | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _EVIDENCE_ID_RE.fullmatch(self.evidence_id):
            raise CapabilityError("evidence_id_invalid")
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("evidence_provider_id_invalid")
        if self.locator.provider_id != self.provider_id:
            raise CapabilityError("evidence_provider_mismatch")
        object.__setattr__(
            self,
            "title",
            _bounded_text(self.title, limit=320, code="evidence_title_invalid"),
        )
        object.__setattr__(
            self,
            "provenance",
            _bounded_text(self.provenance, limit=1024, code="evidence_provenance_invalid"),
        )
        fingerprint = _bounded_text(
            self.fingerprint,
            limit=256,
            code="evidence_fingerprint_invalid",
        )
        if not fingerprint:
            raise CapabilityError("evidence_fingerprint_invalid")
        object.__setattr__(self, "fingerprint", fingerprint)
        if self.captured_at.tzinfo is None:
            object.__setattr__(self, "captured_at", self.captured_at.replace(tzinfo=UTC))
        if self.score is not None and (not math.isfinite(self.score) or self.score < 0):
            raise CapabilityError("evidence_score_invalid")
        conflict_group = _bounded_text(
            self.conflict_group,
            limit=160,
            code="evidence_conflict_group_invalid",
        )
        object.__setattr__(self, "conflict_group", conflict_group)
        object.__setattr__(
            self,
            "citation",
            freeze_json_mapping(self.citation, max_bytes=8 * 1024),
        )
        object.__setattr__(
            self,
            "metadata",
            freeze_json_mapping(self.metadata, max_bytes=16 * 1024),
        )

    def with_freshness(self, freshness: EvidenceFreshness) -> "EvidenceRef":
        return replace(self, freshness=freshness)

    def to_json_value(self, *, include_scope: bool = True) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "evidence_id": self.evidence_id,
            "kind": self.kind.value,
            "provider_id": self.provider_id,
            "locator": self.locator.to_json_value(),
            "title": self.title,
            "provenance": self.provenance,
            "fingerprint": self.fingerprint,
            "captured_at": self.captured_at.astimezone(UTC).isoformat(),
            "freshness": self.freshness.value,
            "trust": self.trust.value,
            "citation": thaw_json(self.citation),
            "conflict_group": self.conflict_group,
            "score": self.score,
            "metadata": thaw_json(self.metadata),
        }
        if include_scope:
            value["access_scope"] = self.access_scope.to_json_value()
        return value


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    ref: EvidenceRef
    excerpt: str = ""
    data: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        excerpt = _bounded_text(
            self.excerpt,
            limit=DEFAULT_MAX_EXCERPT_BYTES,
            code="evidence_excerpt_too_large",
        )
        object.__setattr__(self, "excerpt", excerpt)
        object.__setattr__(
            self,
            "data",
            freeze_json_mapping(self.data, max_bytes=DEFAULT_MAX_EXCERPT_BYTES),
        )
        if len(canonical_json_bytes(self.to_untrusted_projection())) > DEFAULT_MAX_EXCERPT_BYTES * 2:
            raise CapabilityError("evidence_item_too_large")

    def to_untrusted_projection(self) -> dict[str, JsonValue]:
        return {
            "source": "evidence",
            "trust_boundary": "untrusted_data",
            "reference": self.ref.to_json_value(include_scope=False),
            "excerpt": self.excerpt,
            "data": thaw_json(self.data),
        }


@dataclass(frozen=True, slots=True)
class EvidenceSearchRequest:
    query: str
    kinds: tuple[EvidenceKind, ...] = ()
    provider_ids: tuple[str, ...] = ()
    max_results: int = DEFAULT_MAX_RESULTS
    max_excerpt_bytes: int = DEFAULT_MAX_EXCERPT_BYTES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    include_stale: bool = False
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        query = _bounded_text(self.query, limit=4096, code="evidence_query_invalid")
        if not query:
            raise CapabilityError("evidence_query_invalid")
        object.__setattr__(self, "query", query)
        kinds = tuple(dict.fromkeys(EvidenceKind(item) for item in self.kinds))
        provider_ids = tuple(dict.fromkeys(str(item) for item in self.provider_ids))
        if any(not _PROVIDER_ID_RE.fullmatch(item) for item in provider_ids):
            raise CapabilityError("evidence_provider_id_invalid")
        if not 1 <= self.max_results <= DEFAULT_MAX_RESULTS:
            raise CapabilityError("evidence_max_results_invalid")
        if not 0 <= self.max_excerpt_bytes <= DEFAULT_MAX_EXCERPT_BYTES:
            raise CapabilityError("evidence_excerpt_budget_invalid")
        if not 1024 <= self.max_total_bytes <= DEFAULT_MAX_TOTAL_BYTES:
            raise CapabilityError("evidence_total_budget_invalid")
        object.__setattr__(self, "kinds", kinds)
        object.__setattr__(self, "provider_ids", provider_ids)
        object.__setattr__(
            self,
            "metadata",
            freeze_json_mapping(self.metadata, max_bytes=8 * 1024),
        )


@dataclass(frozen=True, slots=True)
class EvidenceSearchResult:
    provider_id: str
    refs: tuple[EvidenceRef, ...]
    truncated: bool = False

    def __post_init__(self) -> None:
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("evidence_provider_id_invalid")
        refs = tuple(self.refs)
        if any(item.provider_id != self.provider_id for item in refs):
            raise CapabilityError("evidence_provider_mismatch")
        if len(refs) > DEFAULT_MAX_RESULTS:
            raise CapabilityError("evidence_result_limit_exceeded")
        object.__setattr__(self, "refs", refs)


@dataclass(frozen=True, slots=True)
class EvidenceProviderStatus:
    provider_id: str
    state: str
    kinds: tuple[EvidenceKind, ...] = ()
    error_code: str = ""

    def __post_init__(self) -> None:
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("evidence_provider_id_invalid")
        if self.state not in {"available", "unavailable", "failed"}:
            raise CapabilityError("evidence_provider_state_invalid")
        if self.state == "available" and self.error_code:
            raise CapabilityError("evidence_provider_state_invalid")
        if self.state != "available" and not self.error_code:
            raise CapabilityError("evidence_provider_state_invalid")


EvidenceSearchCallable: TypeAlias = Callable[
    [CapabilityContext, EvidenceSearchRequest],
    Iterable[EvidenceRef] | EvidenceSearchResult,
]
EvidenceFetchCallable: TypeAlias = Callable[[CapabilityContext, EvidenceRef], EvidenceItem]
EvidenceGuardCallable: TypeAlias = Callable[[CapabilityContext], bool]


@dataclass(frozen=True, slots=True)
class EvidenceProvider:
    provider_id: str
    version: str
    kinds: tuple[EvidenceKind, ...]
    search: EvidenceSearchCallable = field(repr=False, compare=False)
    fetch: EvidenceFetchCallable = field(repr=False, compare=False)
    optional: bool = True
    default_enabled: bool = True
    max_results: int = DEFAULT_MAX_RESULTS
    max_excerpt_bytes: int = DEFAULT_MAX_EXCERPT_BYTES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    timeout_seconds: int | None = None
    guard: EvidenceGuardCallable | None = field(default=None, repr=False, compare=False)
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _PROVIDER_ID_RE.fullmatch(self.provider_id):
            raise CapabilityError("evidence_provider_id_invalid")
        if not re.fullmatch(r"[1-9][0-9]*", self.version):
            raise CapabilityError("evidence_provider_version_invalid")
        kinds = tuple(dict.fromkeys(EvidenceKind(item) for item in self.kinds))
        if not kinds:
            raise CapabilityError("evidence_provider_kinds_required")
        if not callable(self.search) or not callable(self.fetch):
            raise CapabilityError("evidence_provider_callable_invalid")
        if not 1 <= self.max_results <= DEFAULT_MAX_RESULTS:
            raise CapabilityError("evidence_provider_result_limit_invalid")
        if not 0 <= self.max_excerpt_bytes <= DEFAULT_MAX_EXCERPT_BYTES:
            raise CapabilityError("evidence_provider_excerpt_limit_invalid")
        if not 1024 <= self.max_total_bytes <= DEFAULT_MAX_TOTAL_BYTES:
            raise CapabilityError("evidence_provider_total_limit_invalid")
        if self.timeout_seconds is not None and not 1 <= self.timeout_seconds <= 120:
            raise CapabilityError("evidence_provider_timeout_invalid")
        object.__setattr__(self, "kinds", kinds)
        object.__setattr__(
            self,
            "metadata",
            freeze_json_mapping(self.metadata, max_bytes=16 * 1024),
        )


@dataclass(frozen=True, slots=True)
class EvidenceSearchBatch:
    refs: tuple[EvidenceRef, ...]
    results: tuple[EvidenceSearchResult, ...]
    statuses: tuple[EvidenceProviderStatus, ...]


@dataclass(frozen=True, slots=True)
class EvidenceRoutingPolicy:
    """Prioritize evidence classes without classifying the whole user intent."""

    def preferred_kinds(self, request: EvidenceSearchRequest) -> tuple[EvidenceKind, ...]:
        if request.kinds:
            return request.kinds
        query = request.query.casefold()
        if any(token in query for token in ("traceback", "error", "fall", "excep", "latenc")):
            return (
                EvidenceKind.DIAGNOSTIC,
                EvidenceKind.LOG,
                EvidenceKind.RUNTIME,
                EvidenceKind.SOURCE,
                EvidenceKind.XML,
            )
        if any(token in query for token in ("módulo", "modulo", "module", "repo", "instal", "version")):
            return (
                EvidenceKind.RUNTIME,
                EvidenceKind.CONFIGURATION,
                EvidenceKind.DOCUMENT,
                EvidenceKind.SOURCE,
                EvidenceKind.XML,
                EvidenceKind.WEB,
            )
        if any(token in query for token in ("cómo", "como", "how", "configur", "usar", "use")):
            return (
                EvidenceKind.DOCUMENT,
                EvidenceKind.RUNTIME,
                EvidenceKind.CONFIGURATION,
                EvidenceKind.SOURCE,
            )
        return (
            EvidenceKind.BUSINESS_RECORD,
            EvidenceKind.RUNTIME,
            EvidenceKind.SCHEMA,
            EvidenceKind.DOCUMENT,
        )

    def select(
        self,
        request: EvidenceSearchRequest,
        providers: Iterable[EvidenceProvider],
    ) -> tuple[EvidenceProvider, ...]:
        ordered = tuple(providers)
        if request.provider_ids:
            by_id = {item.provider_id: item for item in ordered}
            return tuple(by_id[item] for item in request.provider_ids if item in by_id)
        preference = self.preferred_kinds(request)
        rank = {kind: index for index, kind in enumerate(preference)}

        def provider_rank(provider: EvidenceProvider) -> tuple[int, str]:
            positions = [rank[kind] for kind in provider.kinds if kind in rank]
            return (min(positions) if positions else len(rank) + 1, provider.provider_id)

        return tuple(sorted(ordered, key=provider_rank))


class EvidenceProviderCatalog:
    """Deterministic provider catalog with per-provider failure isolation."""

    def __init__(self, providers: Iterable[EvidenceProvider] = ()) -> None:
        ordered = tuple(sorted(providers, key=lambda item: item.provider_id))
        if len({item.provider_id for item in ordered}) != len(ordered):
            raise CapabilityError("evidence_provider_id_duplicate")
        self._providers = ordered
        self._by_id = {item.provider_id: item for item in ordered}

    def __iter__(self):
        return iter(self._providers)

    def __len__(self) -> int:
        return len(self._providers)

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(item.provider_id for item in self._providers)

    def availability(
        self,
        context: CapabilityContext,
    ) -> tuple[tuple[EvidenceProvider, ...], tuple[EvidenceProviderStatus, ...]]:
        available: list[EvidenceProvider] = []
        statuses: list[EvidenceProviderStatus] = []
        for provider in self._providers:
            if not provider.default_enabled:
                statuses.append(
                    EvidenceProviderStatus(
                        provider_id=provider.provider_id,
                        state="unavailable",
                        kinds=provider.kinds,
                        error_code="evidence_provider_disabled",
                    )
                )
                continue
            try:
                enabled = provider.guard(context) if provider.guard is not None else True
            except Exception:
                enabled = False
                error_code = "evidence_provider_guard_exception"
            else:
                error_code = "evidence_provider_guard_denied"
            if not enabled:
                statuses.append(
                    EvidenceProviderStatus(
                        provider_id=provider.provider_id,
                        state="unavailable",
                        kinds=provider.kinds,
                        error_code=error_code,
                    )
                )
                continue
            available.append(provider)
            statuses.append(
                EvidenceProviderStatus(
                    provider_id=provider.provider_id,
                    state="available",
                    kinds=provider.kinds,
                )
            )
        return tuple(available), tuple(statuses)

    def search(
        self,
        context: CapabilityContext,
        request: EvidenceSearchRequest,
        *,
        routing_policy: EvidenceRoutingPolicy | None = None,
    ) -> EvidenceSearchBatch:
        available, availability_statuses = self.availability(context)
        selected = (routing_policy or EvidenceRoutingPolicy()).select(request, available)
        refs: list[EvidenceRef] = []
        results: list[EvidenceSearchResult] = []
        statuses = {item.provider_id: item for item in availability_statuses}
        used_bytes = 0
        seen: set[str] = set()

        for provider in selected:
            if len(refs) >= request.max_results:
                break
            provider_request = replace(
                request,
                max_results=min(request.max_results - len(refs), provider.max_results),
                max_excerpt_bytes=min(request.max_excerpt_bytes, provider.max_excerpt_bytes),
                max_total_bytes=min(request.max_total_bytes - used_bytes, provider.max_total_bytes),
            )
            try:
                raw = provider.search(context, provider_request)
                result = raw if isinstance(raw, EvidenceSearchResult) else EvidenceSearchResult(
                    provider_id=provider.provider_id,
                    refs=tuple(raw),
                )
                accepted: list[EvidenceRef] = []
                for ref in result.refs:
                    if ref.provider_id != provider.provider_id or ref.kind not in provider.kinds:
                        raise CapabilityError("evidence_provider_result_invalid")
                    if not ref.access_scope.allows(context):
                        continue
                    if ref.freshness in {EvidenceFreshness.REVOKED, EvidenceFreshness.MISSING}:
                        continue
                    if ref.freshness == EvidenceFreshness.STALE and not request.include_stale:
                        continue
                    if ref.evidence_id in seen:
                        continue
                    size = len(canonical_json_bytes(ref.to_json_value(include_scope=False)))
                    if used_bytes + size > request.max_total_bytes:
                        break
                    seen.add(ref.evidence_id)
                    accepted.append(ref)
                    refs.append(ref)
                    used_bytes += size
                    if len(refs) >= request.max_results:
                        break
                results.append(
                    EvidenceSearchResult(
                        provider_id=provider.provider_id,
                        refs=tuple(accepted),
                        truncated=result.truncated or len(accepted) < len(result.refs),
                    )
                )
            except Exception as exc:
                code = exc.args[0] if isinstance(exc, CapabilityError) and exc.args else "evidence_provider_search_failed"
                statuses[provider.provider_id] = EvidenceProviderStatus(
                    provider_id=provider.provider_id,
                    state="failed",
                    kinds=provider.kinds,
                    error_code=str(code)[:160],
                )
                if not provider.optional:
                    raise CapabilityError("required_evidence_provider_failed") from exc

        return EvidenceSearchBatch(
            refs=tuple(refs),
            results=tuple(results),
            statuses=tuple(statuses[item.provider_id] for item in self._providers),
        )

    def fetch(
        self,
        context: CapabilityContext,
        ref: EvidenceRef,
        *,
        source_acl: Iterable[str] = (),
    ) -> EvidenceItem:
        provider = self._by_id.get(ref.provider_id)
        if provider is None:
            raise CapabilityError("evidence_provider_unknown")
        available, _statuses = self.availability(context)
        if provider.provider_id not in {item.provider_id for item in available}:
            raise CapabilityError("evidence_provider_unavailable")
        if not ref.access_scope.allows(context, source_acl=source_acl):
            raise CapabilityError("evidence_access_denied")
        try:
            item = provider.fetch(context, ref)
        except Exception as exc:
            if not provider.optional:
                raise CapabilityError("required_evidence_provider_failed") from exc
            if isinstance(exc, CapabilityError):
                raise
            raise CapabilityError("evidence_provider_fetch_failed") from exc
        if item.ref.provider_id != provider.provider_id:
            raise CapabilityError("evidence_provider_result_invalid")
        if item.ref.locator.canonical_key != ref.locator.canonical_key:
            raise CapabilityError("evidence_locator_mismatch")
        if not item.ref.access_scope.allows(context, source_acl=source_acl):
            raise CapabilityError("evidence_access_denied")
        if item.ref.fingerprint != ref.fingerprint and item.ref.freshness == EvidenceFreshness.CURRENT:
            item = EvidenceItem(
                ref=item.ref.with_freshness(EvidenceFreshness.STALE),
                excerpt=item.excerpt,
                data={
                    **dict(thaw_json(item.data)),
                    "requested_fingerprint": ref.fingerprint,
                    "current_fingerprint": item.ref.fingerprint,
                },
            )
        size = len(canonical_json_bytes(item.to_untrusted_projection()))
        if size > min(provider.max_total_bytes, DEFAULT_MAX_TOTAL_BYTES):
            raise CapabilityError("evidence_item_too_large")
        return item


@dataclass(frozen=True, slots=True)
class EvidenceLedgerSnapshot:
    format_version: int = EVIDENCE_FORMAT_VERSION
    revision: int = 0
    refs: tuple[EvidenceRef, ...] = ()
    items: tuple[EvidenceItem, ...] = ()
    captured_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if self.format_version != EVIDENCE_FORMAT_VERSION:
            raise CapabilityError("evidence_ledger_version_invalid")
        if self.revision < 0:
            raise CapabilityError("evidence_ledger_revision_invalid")
        if len(self.refs) > LEDGER_MAX_REFS or len(self.items) > LEDGER_MAX_EXCERPTS:
            raise CapabilityError("evidence_ledger_limit_exceeded")
        ids = [item.evidence_id for item in self.refs]
        if len(ids) != len(set(ids)):
            raise CapabilityError("evidence_ledger_duplicate")
        ref_ids = set(ids)
        if any(item.ref.evidence_id not in ref_ids for item in self.items):
            raise CapabilityError("evidence_ledger_orphan_item")
        if any(len(item.excerpt.encode("utf-8")) > LEDGER_MAX_EXCERPT_BYTES for item in self.items):
            raise CapabilityError("evidence_ledger_excerpt_limit_exceeded")
        if len(canonical_json_bytes(self.to_json_value())) > LEDGER_MAX_TOTAL_BYTES:
            raise CapabilityError("evidence_ledger_size_exceeded")

    def to_json_value(self) -> dict[str, JsonValue]:
        return {
            "format_version": self.format_version,
            "revision": self.revision,
            "refs": [item.to_json_value() for item in self.refs],
            "items": [item.to_untrusted_projection() for item in self.items],
            "captured_at": self.captured_at.astimezone(UTC).isoformat(),
        }


class EvidenceLedger:
    """Turn-scoped bounded ledger; corpora remain in their owning providers."""

    def __init__(self, snapshot: EvidenceLedgerSnapshot | None = None) -> None:
        snapshot = snapshot or EvidenceLedgerSnapshot()
        self._revision = snapshot.revision
        self._refs = list(snapshot.refs)
        self._items = {item.ref.evidence_id: item for item in snapshot.items}
        self._captured_at = snapshot.captured_at

    def register(
        self,
        value: EvidenceRef | EvidenceItem,
        *,
        retain_excerpt: bool = True,
    ) -> EvidenceLedgerSnapshot:
        ref = value.ref if isinstance(value, EvidenceItem) else value
        existing_index = next(
            (index for index, item in enumerate(self._refs) if item.evidence_id == ref.evidence_id),
            None,
        )
        if existing_index is None:
            if len(self._refs) >= LEDGER_MAX_REFS:
                raise CapabilityError("evidence_ledger_ref_limit_exceeded")
            self._refs.append(ref)
        else:
            existing = self._refs[existing_index]
            if existing.provider_id != ref.provider_id or existing.locator.canonical_key != ref.locator.canonical_key:
                raise CapabilityError("evidence_ledger_identity_conflict")
            self._refs[existing_index] = ref
        if isinstance(value, EvidenceItem) and retain_excerpt:
            bounded_excerpt = value.excerpt
            if len(bounded_excerpt.encode("utf-8")) > LEDGER_MAX_EXCERPT_BYTES:
                encoded = bounded_excerpt.encode("utf-8")[:LEDGER_MAX_EXCERPT_BYTES]
                bounded_excerpt = encoded.decode("utf-8", errors="ignore")
            item = EvidenceItem(ref=ref, excerpt=bounded_excerpt, data=value.data)
            if ref.evidence_id not in self._items and len(self._items) >= LEDGER_MAX_EXCERPTS:
                raise CapabilityError("evidence_ledger_excerpt_count_exceeded")
            self._items[ref.evidence_id] = item
        self._revision += 1
        self._captured_at = utcnow()
        snapshot = self.snapshot()
        return snapshot

    def snapshot(self) -> EvidenceLedgerSnapshot:
        ordered_refs = tuple(self._refs)
        ordered_items = tuple(
            self._items[item.evidence_id]
            for item in ordered_refs
            if item.evidence_id in self._items
        )
        return EvidenceLedgerSnapshot(
            revision=self._revision,
            refs=ordered_refs,
            items=ordered_items,
            captured_at=self._captured_at,
        )


__all__ = [
    "DEFAULT_MAX_EXCERPT_BYTES",
    "DEFAULT_MAX_RESULTS",
    "DEFAULT_MAX_TOTAL_BYTES",
    "EVIDENCE_FORMAT_VERSION",
    "EvidenceAccessScope",
    "EvidenceFetchCallable",
    "EvidenceFreshness",
    "EvidenceGuardCallable",
    "EvidenceItem",
    "EvidenceKind",
    "EvidenceLedger",
    "EvidenceLedgerSnapshot",
    "EvidenceLocator",
    "EvidenceProvider",
    "EvidenceProviderCatalog",
    "EvidenceProviderStatus",
    "EvidenceRef",
    "EvidenceRoutingPolicy",
    "EvidenceSearchBatch",
    "EvidenceSearchCallable",
    "EvidenceSearchRequest",
    "EvidenceSearchResult",
    "EvidenceTrust",
    "canonical_fingerprint",
    "canonical_json_bytes",
    "freeze_json",
    "freeze_json_mapping",
    "redact_secrets",
    "thaw_json",
    "utcnow",
]

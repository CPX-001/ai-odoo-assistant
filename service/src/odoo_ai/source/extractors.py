"""Bounded literal-manifest and Python AST extractors for M3."""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass, field
from typing import cast

from pydantic import JsonValue

from odoo_ai.contracts import (
    ManifestMetadata,
    ManifestStatus,
    SourceFileKind,
    SourceProvenance,
)
from odoo_ai.source.scanner import (
    ExtractedSymbol,
    FileExtraction,
    FileScanContext,
    NoopExtractor,
    SourceExtractionError,
    SourceExtractor,
)


@dataclass(frozen=True, slots=True)
class ParserLimits:
    max_file_bytes: int = 1024 * 1024
    max_ast_nodes: int = 100_000
    max_collection_items: int = 2048
    max_string_chars: int = 32_768
    max_asset_depth: int = 8

    def __post_init__(self) -> None:
        values = (
            self.max_file_bytes,
            self.max_ast_nodes,
            self.max_collection_items,
            self.max_string_chars,
            self.max_asset_depth,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("parser limits must be positive integers")


@dataclass(frozen=True, slots=True)
class ProvenanceEvidence:
    """Explicit facts only; directory names never participate."""

    official_modules: frozenset[str] = frozenset()
    oca_modules: frozenset[str] = frozenset()
    remote_known_modules: frozenset[str] = frozenset()
    manual_rules: dict[str, SourceProvenance] = field(default_factory=dict)


def classify_module_provenance(
    module: str, evidence: ProvenanceEvidence | None = None
) -> SourceProvenance:
    facts = evidence or ProvenanceEvidence()
    if module in facts.official_modules:
        return SourceProvenance.OFFICIAL
    if module in facts.oca_modules:
        return SourceProvenance.OCA
    if module in facts.remote_known_modules:
        return SourceProvenance.REMOTE_KNOWN
    if module in facts.manual_rules:
        return facts.manual_rules[module]
    return SourceProvenance.UNKNOWN


class ManifestExtractor:
    """Evaluate only one literal manifest dictionary via ast.literal_eval."""

    def __init__(self, limits: ParserLimits | None = None) -> None:
        self._limits = limits or ParserLimits()

    def extract(self, context: FileScanContext) -> FileExtraction:
        if context.kind is not SourceFileKind.MANIFEST:
            raise SourceExtractionError("wrong_extractor")
        tree = _parse_bounded(context, self._limits)
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Expr):
            return _manifest_result(ManifestMetadata(status=ManifestStatus.UNEVALUABLE))
        try:
            value = ast.literal_eval(tree.body[0].value)
        except (ValueError, TypeError, MemoryError, RecursionError):
            return _manifest_result(ManifestMetadata(status=ManifestStatus.UNEVALUABLE))
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            return _manifest_result(ManifestMetadata(status=ManifestStatus.UNEVALUABLE))
        try:
            metadata = ManifestMetadata(
                status=ManifestStatus.EVALUATED,
                name=_optional_text(value.get("name"), 512, self._limits),
                version=_optional_text(value.get("version"), 128, self._limits),
                depends=_text_list(value.get("depends"), self._limits),
                data=_text_list(value.get("data"), self._limits),
                assets=_assets(value.get("assets"), self._limits),
                license=_optional_text(value.get("license"), 128, self._limits),
            )
        except (TypeError, ValueError):
            raise SourceExtractionError("invalid_manifest") from None
        return _manifest_result(metadata)


class PythonAstExtractor:
    """Extract structural Odoo symbols without importing or executing source."""

    def __init__(self, limits: ParserLimits | None = None) -> None:
        self._limits = limits or ParserLimits()

    def extract(self, context: FileScanContext) -> FileExtraction:
        if context.kind is not SourceFileKind.PYTHON:
            raise SourceExtractionError("wrong_extractor")
        tree = _parse_bounded(context, self._limits)
        symbols: list[ExtractedSymbol] = []
        symbols.extend(_import_symbols(tree))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and _odoo_class(node):
                symbols.extend(_class_symbols(node))
        return FileExtraction(symbols=_deduplicate_symbols(symbols))


def m3_source_extractors(
    limits: ParserLimits | None = None,
) -> dict[SourceFileKind, SourceExtractor]:
    """Explicit extractor map; XML/CSV remain bounded stubs until M3-05."""

    parser_limits = limits or ParserLimits()
    return {
        SourceFileKind.MANIFEST: ManifestExtractor(parser_limits),
        SourceFileKind.PYTHON: PythonAstExtractor(parser_limits),
        SourceFileKind.XML: NoopExtractor(),
        SourceFileKind.CSV: NoopExtractor(),
    }


def _parse_bounded(context: FileScanContext, limits: ParserLimits) -> ast.Module:
    if context.size_bytes != len(context.content) or len(context.content) > limits.max_file_bytes:
        raise SourceExtractionError("file_too_large")
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(context.content).readline)
        source = context.content.decode(encoding)
    except (LookupError, SyntaxError, UnicodeError):
        raise SourceExtractionError("decode_error") from None
    try:
        tree = ast.parse(source, filename=context.logical_path, mode="exec")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        raise SourceExtractionError("syntax_error") from None
    if sum(1 for _ in ast.walk(tree)) > limits.max_ast_nodes:
        raise SourceExtractionError("ast_node_limit_exceeded")
    return tree


def _manifest_result(metadata: ManifestMetadata) -> FileExtraction:
    dumped = metadata.model_dump(mode="json")
    return FileExtraction(metadata=cast(dict[str, JsonValue], dumped))


def _optional_text(value: object, maximum: int, limits: ParserLimits) -> str | None:
    if value is None or value is False:
        return None
    if (
        not isinstance(value, str)
        or len(value) > min(maximum, limits.max_string_chars)
        or any(ord(character) < 32 and character not in "\t\n\r" for character in value)
    ):
        raise ValueError
    return value


def _text_list(value: object, limits: ParserLimits) -> tuple[str, ...]:
    if value is None or value is False:
        return ()
    if not isinstance(value, (list, tuple)) or len(value) > limits.max_collection_items:
        raise ValueError
    parsed = tuple(_optional_text(item, 1024, limits) for item in value)
    if any(item is None for item in parsed):
        raise ValueError
    return cast(tuple[str, ...], parsed)


def _assets(value: object, limits: ParserLimits) -> dict[str, JsonValue]:
    if value is None or value is False:
        return {}
    if not isinstance(value, dict) or len(value) > 512:
        raise ValueError
    budget = [limits.max_collection_items]
    result: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str) or len(key) > 512:
            raise ValueError
        result[key] = _asset_value(item, limits, budget, depth=0)
    return result


def _asset_value(
    value: object,
    limits: ParserLimits,
    budget: list[int],
    *,
    depth: int,
) -> JsonValue:
    if depth > limits.max_asset_depth or budget[0] <= 0:
        raise ValueError
    budget[0] -= 1
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > limits.max_string_chars:
            raise ValueError
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > limits.max_collection_items:
            raise ValueError
        return [
            _asset_value(item, limits, budget, depth=depth + 1) for item in value
        ]
    if isinstance(value, dict):
        if len(value) > limits.max_collection_items or not all(
            isinstance(key, str) for key in value
        ):
            raise ValueError
        return {
            key: _asset_value(item, limits, budget, depth=depth + 1)
            for key, item in value.items()
        }
    raise ValueError


def _import_symbols(tree: ast.Module) -> list[ExtractedSymbol]:
    symbols: list[ExtractedSymbol] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            names = [f"{prefix}.{alias.name}".strip(".") for alias in node.names]
        else:
            continue
        for name in names:
            symbols.append(_symbol("import", None, name, node))
    return symbols


def _odoo_class(node: ast.ClassDef) -> bool:
    assigned = {
        target.id
        for statement in node.body
        for target in _assignment_targets(statement)
    }
    if assigned.intersection({"_name", "_inherit"}):
        return True
    return any(
        (_dotted_name(base) or "").split(".")[-1]
        in {"Model", "AbstractModel", "TransientModel"}
        for base in node.bases
    )


def _class_symbols(node: ast.ClassDef) -> list[ExtractedSymbol]:
    model_name: str | None = None
    inherits: tuple[str, ...] = ()
    name_statement: ast.stmt | None = None
    inherit_statement: ast.stmt | None = None
    for statement in node.body:
        assigned = {target.id for target in _assignment_targets(statement)}
        value = _assignment_value(statement)
        if "_name" in assigned:
            model_name = _literal_model_name(value)
            name_statement = statement
        if "_inherit" in assigned:
            inherits = _literal_model_names(value)
            inherit_statement = statement
    targets: tuple[str | None, ...] = (
        (model_name,) if model_name is not None else inherits or (None,)
    )
    symbols = [_symbol("class", targets[0], node.name, node)]
    if model_name is not None and name_statement is not None:
        symbols.append(_symbol("model", model_name, model_name, name_statement))
    if inherit_statement is not None:
        symbols.extend(
            _symbol("inherit", inherited, inherited, inherit_statement)
            for inherited in inherits
        )

    for statement in node.body:
        field_names = _field_names(statement)
        for field_name in field_names:
            symbols.extend(
                _symbol("field", target, field_name, statement) for target in targets
            )
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.extend(
                _symbol("method", target, statement.name, statement)
                for target in targets
            )
            for decorator in statement.decorator_list:
                decorator_name = _dotted_name(
                    decorator.func if isinstance(decorator, ast.Call) else decorator
                )
                if decorator_name:
                    symbols.extend(
                        _symbol("decorator", target, decorator_name, decorator)
                        for target in targets
                    )
    return symbols


def _assignment_targets(statement: ast.stmt) -> tuple[ast.Name, ...]:
    if isinstance(statement, ast.Assign):
        return tuple(target for target in statement.targets if isinstance(target, ast.Name))
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        return (statement.target,)
    return ()


def _assignment_value(statement: ast.stmt) -> ast.expr | None:
    if isinstance(statement, (ast.Assign, ast.AnnAssign)):
        return statement.value
    return None


def _literal_model_name(value: ast.expr | None) -> str | None:
    names = _literal_model_names(value)
    return names[0] if len(names) == 1 else None


def _literal_model_names(value: ast.expr | None) -> tuple[str, ...]:
    if value is None:
        return ()
    try:
        literal = ast.literal_eval(value)
    except (ValueError, TypeError, MemoryError, RecursionError):
        return ()
    if isinstance(literal, str):
        values = (literal,)
    elif isinstance(literal, (list, tuple)):
        values = tuple(literal)
    else:
        return ()
    if any(not isinstance(item, str) or not 1 <= len(item) <= 255 for item in values):
        return ()
    return cast(tuple[str, ...], tuple(dict.fromkeys(values)))


def _field_names(statement: ast.stmt) -> tuple[str, ...]:
    value = _assignment_value(statement)
    if not isinstance(value, ast.Call):
        return ()
    function = _dotted_name(value.func)
    if function is None or len(function.split(".")) < 2:
        return ()
    if function.split(".")[-2] != "fields":
        return ()
    return tuple(target.id for target in _assignment_targets(statement))


def _dotted_name(node: ast.expr) -> str | None:
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _symbol(
    kind: str,
    model: str | None,
    name: str,
    node: ast.AST,
) -> ExtractedSymbol:
    start_line = getattr(node, "lineno", 1)
    end_line = getattr(node, "end_lineno", None) or start_line
    return ExtractedSymbol(kind, model, name, start_line, end_line)


def _deduplicate_symbols(
    symbols: list[ExtractedSymbol],
) -> tuple[ExtractedSymbol, ...]:
    unique = {
        (
            symbol.kind,
            symbol.model,
            symbol.name,
            symbol.start_line,
            symbol.end_line,
        ): symbol
        for symbol in symbols
    }
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.start_line,
                item.end_line,
                item.kind,
                item.name,
                item.model or "",
            ),
        )
    )

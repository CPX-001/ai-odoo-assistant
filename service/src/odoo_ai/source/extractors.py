"""Bounded literal-manifest and Python AST extractors for M3."""

from __future__ import annotations

import ast
import csv
import io
import tokenize
import xml.parsers.expat as expat
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
    ExtractedXmlRecord,
    FileExtraction,
    FileScanContext,
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
    max_xml_depth: int = 64
    max_xml_nodes: int = 50_000
    max_xml_attributes: int = 32
    max_csv_rows: int = 10_000
    max_csv_columns: int = 32
    max_csv_field_chars: int = 4096

    def __post_init__(self) -> None:
        values = (
            self.max_file_bytes,
            self.max_ast_nodes,
            self.max_collection_items,
            self.max_string_chars,
            self.max_asset_depth,
            self.max_xml_depth,
            self.max_xml_nodes,
            self.max_xml_attributes,
            self.max_csv_rows,
            self.max_csv_columns,
            self.max_csv_field_chars,
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


@dataclass(slots=True)
class _XmlNode:
    tag: str
    attributes: dict[str, str]
    start_line: int
    end_line: int | None = None
    text: list[str] = field(default_factory=list)
    children: list[_XmlNode] = field(default_factory=list)


class XmlExtractor:
    """Parse bounded Odoo declarations with Expat and no external entities."""

    def __init__(self, limits: ParserLimits | None = None) -> None:
        self._limits = limits or ParserLimits()

    def extract(self, context: FileScanContext) -> FileExtraction:
        if context.kind is not SourceFileKind.XML:
            raise SourceExtractionError("wrong_extractor")
        roots = _parse_xml_tree(context, self._limits)
        symbols: list[ExtractedSymbol] = []
        records: list[ExtractedXmlRecord] = []
        for node in _walk_xml(roots):
            extracted = _xml_declaration(context.module, node, self._limits)
            if extracted is None:
                continue
            record, declared_symbols = extracted
            records.append(record)
            symbols.extend(declared_symbols)
        unique_records = {record.xml_id: record for record in records}
        return FileExtraction(
            symbols=_deduplicate_symbols(symbols),
            xml_records=tuple(unique_records.values()),
            metadata={
                "parser": "expat_no_entities",
                "xml_declarations": len(unique_records),
                "runtime_state_authoritative": True,
            },
        )


class SecurityCsvExtractor:
    """Index static ACL declarations without treating them as effective grants."""

    _headers = (
        "id",
        "name",
        "model_id:id",
        "group_id:id",
        "perm_read",
        "perm_write",
        "perm_create",
        "perm_unlink",
    )

    def __init__(self, limits: ParserLimits | None = None) -> None:
        self._limits = limits or ParserLimits()

    def extract(self, context: FileScanContext) -> FileExtraction:
        if context.kind is not SourceFileKind.CSV:
            raise SourceExtractionError("wrong_extractor")
        _check_file_size(context, self._limits)
        try:
            text = context.content.decode("utf-8-sig")
            rows = csv.reader(io.StringIO(text, newline=""), strict=True)
            header = next(rows)
        except (UnicodeError, csv.Error, StopIteration):
            raise SourceExtractionError("csv_parse_error") from None
        if len(header) > self._limits.max_csv_columns or len(header) != len(set(header)):
            raise SourceExtractionError("csv_column_limit_exceeded")
        security_path = (
            context.logical_path.rsplit("/", maxsplit=1)[-1]
            == "ir.model.access.csv"
            or "/security/" in f"/{context.logical_path}"
        )
        if not set(self._headers).issubset(header):
            if security_path:
                raise SourceExtractionError("csv_security_header_invalid")
            return FileExtraction(metadata={"parser": "csv", "security_csv": False})
        positions = {name: header.index(name) for name in self._headers}
        symbols: list[ExtractedSymbol] = []
        try:
            for row_number, row in enumerate(rows, start=2):
                if row_number - 1 > self._limits.max_csv_rows:
                    raise SourceExtractionError("csv_row_limit_exceeded")
                if len(row) != len(header) or len(row) > self._limits.max_csv_columns:
                    raise SourceExtractionError("csv_row_invalid")
                if any(len(value) > self._limits.max_csv_field_chars for value in row):
                    raise SourceExtractionError("csv_field_limit_exceeded")
                external_id = row[positions["id"]].strip()
                model_external_id = row[positions["model_id:id"]].strip()
                group_external_id = row[positions["group_id:id"]].strip() or None
                if not external_id or not model_external_id:
                    raise SourceExtractionError("csv_row_invalid")
                flags: dict[str, JsonValue] = {
                    flag.removeprefix("perm_"): _acl_flag(row[positions[flag]])
                    for flag in self._headers[-4:]
                }
                qualified_id = _qualify_xml_id(context.module, external_id)
                details: dict[str, JsonValue] = {
                    "declaration": "static_acl",
                    "external_id": qualified_id,
                    "model_external_id": model_external_id,
                    "group_external_id": group_external_id,
                    "permissions": flags,
                    "runtime_effective": False,
                }
                symbols.append(
                    ExtractedSymbol(
                        "acl",
                        model_external_id,
                        qualified_id,
                        row_number,
                        row_number,
                        details,
                    )
                )
        except csv.Error:
            raise SourceExtractionError("csv_parse_error") from None
        return FileExtraction(
            symbols=_deduplicate_symbols(symbols),
            metadata={
                "parser": "csv",
                "security_csv": True,
                "static_acl_declarations": len(symbols),
                "runtime_state_authoritative": True,
            },
        )


def m3_source_extractors(
    limits: ParserLimits | None = None,
) -> dict[SourceFileKind, SourceExtractor]:
    """Explicit bounded extractor map for the complete M3 source index."""

    parser_limits = limits or ParserLimits()
    return {
        SourceFileKind.MANIFEST: ManifestExtractor(parser_limits),
        SourceFileKind.PYTHON: PythonAstExtractor(parser_limits),
        SourceFileKind.XML: XmlExtractor(parser_limits),
        SourceFileKind.CSV: SecurityCsvExtractor(parser_limits),
    }


def _check_file_size(context: FileScanContext, limits: ParserLimits) -> None:
    if context.size_bytes != len(context.content) or len(context.content) > limits.max_file_bytes:
        raise SourceExtractionError("file_too_large")


def _parse_xml_tree(
    context: FileScanContext, limits: ParserLimits
) -> tuple[_XmlNode, ...]:
    _check_file_size(context, limits)
    lowered = context.content.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise SourceExtractionError("xml_forbidden_declaration")
    parser = expat.ParserCreate(namespace_separator="}")
    parser.buffer_text = True
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    roots: list[_XmlNode] = []
    stack: list[_XmlNode] = []
    node_count = 0

    def start(name: str, attributes: dict[str, str]) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > limits.max_xml_nodes:
            raise SourceExtractionError("xml_node_limit_exceeded")
        if len(stack) + 1 > limits.max_xml_depth:
            raise SourceExtractionError("xml_depth_limit_exceeded")
        if len(attributes) > limits.max_xml_attributes or any(
            len(key) > 255 or len(value) > limits.max_string_chars
            for key, value in attributes.items()
        ):
            raise SourceExtractionError("xml_attribute_limit_exceeded")
        node = _XmlNode(_local_xml_name(name), dict(attributes), parser.CurrentLineNumber)
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    def end(name: str) -> None:
        del name
        if not stack:
            raise SourceExtractionError("xml_parse_error")
        node = stack.pop()
        node.end_line = parser.CurrentLineNumber

    def text(value: str) -> None:
        if stack and value:
            stack[-1].text.append(value)

    def external_entity(*args: object) -> int:
        del args
        return 0

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text
    parser.ExternalEntityRefHandler = external_entity
    try:
        parser.Parse(context.content, True)
    except SourceExtractionError:
        raise
    except (expat.ExpatError, LookupError, UnicodeError, ValueError):
        raise SourceExtractionError("xml_parse_error") from None
    if stack:
        raise SourceExtractionError("xml_parse_error")
    return tuple(roots)


def _walk_xml(nodes: tuple[_XmlNode, ...] | list[_XmlNode]) -> tuple[_XmlNode, ...]:
    result: list[_XmlNode] = []
    stack = list(reversed(nodes))
    while stack:
        node = stack.pop()
        result.append(node)
        stack.extend(reversed(node.children))
    return tuple(result)


def _local_xml_name(value: str) -> str:
    return value.rsplit("}", maxsplit=1)[-1]


def _xml_declaration(
    module: str, node: _XmlNode, limits: ParserLimits
) -> tuple[ExtractedXmlRecord, list[ExtractedSymbol]] | None:
    raw_id = node.attributes.get("id")
    if raw_id is None or node.tag not in {
        "record",
        "template",
        "menuitem",
        "act_window",
        "report",
        "url",
        "server",
        "client",
    }:
        return None
    xml_id = _qualify_xml_id(module, raw_id)
    if not 1 <= len(xml_id) <= 255:
        raise SourceExtractionError("xml_identifier_invalid")
    model = node.attributes.get("model")
    if node.tag == "template":
        model = "ir.ui.view"
    elif node.tag == "menuitem":
        model = "ir.ui.menu"
    elif node.tag != "record":
        model = f"ir.actions.{node.tag}"
    if model is not None and not 1 <= len(model) <= 255:
        raise SourceExtractionError("xml_model_invalid")

    fields = {
        child.attributes.get("name", ""): child
        for child in node.children
        if child.tag == "field" and child.attributes.get("name")
    }
    inherit_id = node.attributes.get("inherit_id") or _field_reference(
        fields.get("inherit_id")
    )
    view_model = _bounded_node_text(fields.get("model"), limits)
    xpath_nodes = [child for child in _walk_xml(node.children) if child.tag == "xpath"]
    xpath_expressions = tuple(
        expression
        for child in xpath_nodes
        if (expression := child.attributes.get("expr"))
        and len(expression) <= limits.max_string_chars
    )
    groups = _declared_groups(module, node, fields)
    declaration: dict[str, JsonValue] = {
        "declaration_kind": node.tag,
        "runtime_effective": False,
    }
    if inherit_id:
        declaration["inherit_id"] = _qualify_xml_id(module, inherit_id)
    if view_model:
        declaration["view_model"] = view_model
    if xpath_expressions:
        declaration["xpath"] = list(xpath_expressions)
    if groups:
        declaration["groups"] = list(groups)
    for key in ("name", "res_model", "binding_model", "parent", "action", "sequence"):
        value = node.attributes.get(key)
        if value and len(value) <= limits.max_string_chars:
            declaration[key] = value

    start_line = max(node.start_line, 1)
    end_line = max(node.end_line or start_line, start_line)
    effective_model = view_model or model
    details: dict[str, JsonValue] = {
        "declaration": node.tag,
        "runtime_effective": False,
    }
    symbols = [
        ExtractedSymbol(
            "xml_id", effective_model, xml_id, start_line, end_line, details
        )
    ]
    if inherit_id:
        inherited = _qualify_xml_id(module, inherit_id)
        symbols.append(
            ExtractedSymbol(
                "view_inherit",
                view_model,
                inherited,
                start_line,
                end_line,
                    cast(
                        dict[str, JsonValue],
                        {"declared_by": xml_id, "runtime_order_checked": False},
                    ),
            )
        )
    for xpath_node, expression in zip(xpath_nodes, xpath_expressions, strict=False):
        if len(expression) <= 255:
            xpath_line = max(xpath_node.start_line, 1)
            symbols.append(
                ExtractedSymbol(
                    "xpath",
                    view_model,
                    expression,
                    xpath_line,
                    max(xpath_node.end_line or xpath_line, xpath_line),
                    {"declared_by": xml_id},
                )
            )
    specialized = _xml_specialized_kind(node.tag, model)
    if specialized is not None:
        symbols.append(
            ExtractedSymbol(
                specialized,
                effective_model,
                xml_id,
                start_line,
                end_line,
                details,
            )
        )
    for group in groups:
        if len(group) <= 255:
            symbols.append(
                ExtractedSymbol(
                    "group_restriction",
                    effective_model,
                    group,
                    start_line,
                    end_line,
                    cast(
                        dict[str, JsonValue],
                        {"declared_by": xml_id, "runtime_effective": False},
                    ),
                )
            )
    record = ExtractedXmlRecord(
        xml_id,
        effective_model,
        start_line,
        end_line,
        declaration,
    )
    return record, symbols


def _xml_specialized_kind(tag: str, model: str | None) -> str | None:
    if tag == "menuitem":
        return "menu"
    if tag in {"act_window", "report", "url", "server", "client"} or (
        model is not None and model.startswith("ir.actions.")
    ):
        return "action"
    if model == "res.groups":
        return "group"
    if model == "ir.ui.view" or tag == "template":
        return "view"
    return None


def _field_reference(node: _XmlNode | None) -> str | None:
    if node is None:
        return None
    return node.attributes.get("ref")


def _bounded_node_text(node: _XmlNode | None, limits: ParserLimits) -> str | None:
    if node is None:
        return None
    value = "".join(node.text).strip()
    if not value:
        return None
    if len(value) > limits.max_string_chars:
        raise SourceExtractionError("xml_text_limit_exceeded")
    return value


def _declared_groups(
    module: str, node: _XmlNode, fields: dict[str, _XmlNode]
) -> tuple[str, ...]:
    values: list[str] = []
    raw = node.attributes.get("groups", "")
    values.extend(part.strip().removeprefix("!") for part in raw.split(",") if part.strip())
    group_field = fields.get("groups")
    if group_field is not None:
        reference = group_field.attributes.get("ref")
        if reference:
            values.append(reference)
    return tuple(
        dict.fromkeys(_qualify_xml_id(module, value) for value in values if value)
    )


def _qualify_xml_id(module: str, value: str) -> str:
    stripped = value.strip()
    return stripped if "." in stripped else f"{module}.{stripped}"


def _acl_flag(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"1", "true"}:
        return True
    if normalized in {"0", "false"}:
        return False
    raise SourceExtractionError("csv_permission_invalid")


def _parse_bounded(context: FileScanContext, limits: ParserLimits) -> ast.Module:
    _check_file_size(context, limits)
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

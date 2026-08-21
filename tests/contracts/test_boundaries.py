import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "service" / "src" / "odoo_ai"

CONTRACTS_FORBIDDEN_IMPORTS = {
    "codex",
    "fastapi",
    "odoo",
    "sqlalchemy",
    "storage",
    "odoo_ai.storage",
}
INTERNAL_PORT_IMPORTS = ("odoo_ai.contracts", "odoo_ai.ports")
INTERNAL_APPLICATION_IMPORTS = (
    "odoo_ai.application",
    "odoo_ai.contracts",
    "odoo_ai.ports",
)
VERSIONED_SCHEMA_CLASS = re.compile(r"^[A-Z][A-Za-z0-9_]*(?:18|19)$")


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _matches_prefix(module: str, prefixes: set[str] | tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def _forbidden_imports(source: str, forbidden: set[str]) -> set[str]:
    return {
        prefix
        for module in _imported_modules(source)
        for prefix in forbidden
        if _matches_prefix(module, {prefix})
    }


def _unexpected_layer_imports(source: str, internal_allowed: tuple[str, ...]) -> set[str]:
    unexpected: set[str] = set()
    for module in _imported_modules(source):
        root = module.partition(".")[0]
        if root in sys.stdlib_module_names or _matches_prefix(module, internal_allowed):
            continue
        unexpected.add(module)
    return unexpected


def test_contracts_do_not_import_prohibited_technologies() -> None:
    violations: dict[str, list[str]] = {}
    for path in _python_files(PACKAGE_ROOT / "contracts"):
        forbidden = _forbidden_imports(
            path.read_text(encoding="utf-8"), CONTRACTS_FORBIDDEN_IMPORTS
        )
        if forbidden:
            violations[str(path.relative_to(REPO_ROOT))] = sorted(forbidden)

    assert violations == {}


def test_ports_only_import_stdlib_contracts_or_other_ports() -> None:
    violations: dict[str, list[str]] = {}
    for path in _python_files(PACKAGE_ROOT / "ports"):
        unexpected = _unexpected_layer_imports(
            path.read_text(encoding="utf-8"),
            INTERNAL_PORT_IMPORTS,
        )
        if unexpected:
            violations[str(path.relative_to(REPO_ROOT))] = sorted(unexpected)

    assert violations == {}


def test_application_only_imports_allowed_layers_when_present() -> None:
    application_root = PACKAGE_ROOT / "application"
    if not application_root.exists():
        return

    violations: dict[str, list[str]] = {}
    for path in _python_files(application_root):
        unexpected = _unexpected_layer_imports(
            path.read_text(encoding="utf-8"),
            INTERNAL_APPLICATION_IMPORTS,
        )
        if unexpected:
            violations[str(path.relative_to(REPO_ROOT))] = sorted(unexpected)

    assert violations == {}


def test_no_static_schema_classes_are_named_for_odoo_major_versions() -> None:
    violations: list[str] = []
    for path in _python_files(PACKAGE_ROOT):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and VERSIONED_SCHEMA_CLASS.fullmatch(node.name):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}:{node.name}")

    assert violations == []


def test_forbidden_import_detector_catches_a_regression() -> None:
    source = (
        "from fastapi import FastAPI\n"
        "from odoo_ai import storage\n"
        "from odoo_ai.contracts import Evidence\n"
    )

    assert _forbidden_imports(source, CONTRACTS_FORBIDDEN_IMPORTS) == {
        "fastapi",
        "odoo_ai.storage",
    }

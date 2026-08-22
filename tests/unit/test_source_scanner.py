import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from odoo_ai.contracts import SourceCapabilityState, SourceFileKind
from odoo_ai.source import (
    FileExtraction,
    ResolvedSourceRoot,
    RootOrigin,
    RootSelection,
    ScanLimits,
    SourceScanner,
    StoredSourceFile,
    locate_installed_modules,
    resolve_source_roots,
    source_root_overrides_from_env,
)


class FakeStore:
    def __init__(self) -> None:
        self.files: dict[tuple[str, str], tuple[UUID, str]] = {}
        self.scans: list[UUID] = []
        self.capabilities: list[SourceCapabilityState] = []
        self.replacements: list[UUID] = []

    def open_scan(self, *, instance_profile_id: UUID) -> UUID:
        del instance_profile_id
        scan_id = uuid4()
        self.scans.append(scan_id)
        return scan_id

    def upsert_file(
        self,
        *,
        scan_run_id: UUID,
        module: str,
        logical_path: str,
        kind: SourceFileKind,
        fingerprint: str,
        size_bytes: int,
    ) -> StoredSourceFile:
        del scan_run_id, kind, size_bytes
        key = (module, logical_path)
        previous = self.files.get(key)
        file_id = previous[0] if previous else uuid4()
        changed = previous is None or previous[1] != fingerprint
        self.files[key] = (file_id, fingerprint)
        return StoredSourceFile(file_id=file_id, fingerprint_changed=changed)

    def replace_derivatives(self, *, source_file_id, symbols, xml_records) -> None:
        del symbols, xml_records
        self.replacements.append(source_file_id)

    def mark_stale(self, *, scan_run_id: UUID, seen_file_ids: set[UUID]) -> int:
        del scan_run_id, seen_file_ids
        return 0

    def finish_scan(
        self,
        *,
        scan_run_id: UUID,
        succeeded: bool,
        fingerprint: str | None,
        error_code: str | None,
    ) -> None:
        assert scan_run_id in self.scans
        assert succeeded is (fingerprint is not None)
        assert error_code is None if succeeded else error_code is not None

    def record_capability(
        self, *, instance_profile_id: UUID, state: SourceCapabilityState
    ) -> None:
        del instance_profile_id
        self.capabilities.append(state)


class CountingExtractor:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def extract(self, context) -> FileExtraction:
        self.paths.append(context.logical_path)
        return FileExtraction()


def _module(root: Path, name: str, python_text: str = "VALUE = 1\n") -> Path:
    module = root / name
    (module / "models").mkdir(parents=True)
    (module / "__manifest__.py").write_text("{'name': 'Fixture'}\n", encoding="utf-8")
    (module / "models" / "model.py").write_text(python_text, encoding="utf-8")
    return module


def test_root_priority_override_and_nondefault_layout(tmp_path: Path) -> None:
    conventional = tmp_path / "usr" / "lib" / "odoo" / "addons"
    customer = tmp_path / "srv" / "acme erp" / "extensions"
    conventional.mkdir(parents=True)
    customer.mkdir(parents=True)

    resolution = resolve_source_roots(
        RootSelection(override=(customer,), config=(conventional,))
    )

    assert resolution.selected_origin is RootOrigin.OVERRIDE
    assert [root.path for root in resolution.roots] == [customer.resolve()]


def test_root_states_duplicates_and_permission_are_explicit(tmp_path: Path) -> None:
    root = tmp_path / "addons"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)

    deduplicated = resolve_source_roots(RootSelection(runtime=(root, alias)))
    missing = resolve_source_roots(RootSelection(runtime=(tmp_path / "missing",)))
    denied = resolve_source_roots(
        RootSelection(runtime=(root,)),
        probe=lambda path: SourceCapabilityState.NO_PERMISSION,
    )

    assert len(deduplicated.roots) == 1
    assert missing.issues[0].state is SourceCapabilityState.NOT_FOUND
    assert denied.issues[0].state is SourceCapabilityState.NO_PERMISSION


def test_module_inventory_rejects_symlink_escape_and_ignores_uninstalled(tmp_path: Path) -> None:
    root = tmp_path / "addons"
    root.mkdir()
    _module(root, "installed_module")
    _module(root, "available_only")
    external = tmp_path / "external"
    _module(external, "escaped")
    (root / "escaped").symlink_to(external / "escaped", target_is_directory=True)
    resolved = ResolvedSourceRoot(root.resolve(), RootOrigin.RUNTIME)

    inventory = locate_installed_modules(
        (resolved,),
        ("installed_module", "escaped"),
        max_modules=10,
    )

    assert [module.name for module in inventory.modules] == ["installed_module"]
    assert "available_only" not in {module.name for module in inventory.modules}
    assert any(error.code == "module_symlink_escape" for error in inventory.issues)


def test_incremental_scan_skips_unchanged_and_reextracts_changed_hash(tmp_path: Path) -> None:
    root = tmp_path / "customer-layout" / "addons"
    module = _module(root, "sale_fixture")
    store = FakeStore()
    extractor = CountingExtractor()
    scanner = SourceScanner(
        store=store,
        extractors={
            SourceFileKind.MANIFEST: extractor,
            SourceFileKind.PYTHON: extractor,
        },
        limits=ScanLimits(max_modules=5, max_files=10, max_total_bytes=10_000),
    )
    arguments = {
        "instance_profile_id": uuid4(),
        "roots": RootSelection(override=(root,)),
        "installed_modules": ("sale_fixture",),
    }

    first = scanner.run(**arguments)
    second = scanner.run(**arguments)
    (module / "models" / "model.py").write_text("VALUE = 2\n", encoding="utf-8")
    third = scanner.run(**arguments)

    assert first.capability is SourceCapabilityState.DETECTED
    assert first.metrics.files_extracted == 2
    assert second.metrics.files_extracted == 0
    assert second.metrics.files_unchanged == 2
    assert third.metrics.files_extracted == 1
    assert len(extractor.paths) == 3
    assert store.capabilities == [SourceCapabilityState.DETECTED] * 3


def test_missing_and_denied_roots_update_distinct_capabilities(tmp_path: Path) -> None:
    store = FakeStore()
    missing_scanner = SourceScanner(store=store, extractors={})
    missing = missing_scanner.run(
        instance_profile_id=uuid4(),
        roots=RootSelection(override=(tmp_path / "missing",)),
        installed_modules=("base",),
    )
    denied_scanner = SourceScanner(
        store=store,
        extractors={},
        root_probe=lambda path: SourceCapabilityState.NO_PERMISSION,
    )
    denied = denied_scanner.run(
        instance_profile_id=uuid4(),
        roots=RootSelection(override=(tmp_path,)),
        installed_modules=("base",),
    )

    assert missing.capability is SourceCapabilityState.NOT_FOUND
    assert denied.capability is SourceCapabilityState.NO_PERMISSION


def test_source_root_env_override_is_strict_json() -> None:
    assert source_root_overrides_from_env(
        {"ODOO_AI_SOURCE_ROOTS": '["/srv/customer/addons","/mnt/oca"]'}
    ) == ("/srv/customer/addons", "/mnt/oca")
    with pytest.raises(ValueError, match="JSON list"):
        source_root_overrides_from_env({"ODOO_AI_SOURCE_ROOTS": "/srv/addons"})


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_file_symlink_escape_is_not_read(tmp_path: Path) -> None:
    root = tmp_path / "addons"
    module = _module(root, "fixture")
    secret = tmp_path / "outside.py"
    secret.write_text("SECRET = 'not indexed'\n", encoding="utf-8")
    (module / "models" / "escape.py").symlink_to(secret)
    extractor = CountingExtractor()
    scanner = SourceScanner(
        store=FakeStore(),
        extractors={
            SourceFileKind.MANIFEST: extractor,
            SourceFileKind.PYTHON: extractor,
        },
    )

    result = scanner.run(
        instance_profile_id=uuid4(),
        roots=RootSelection(override=(root,)),
        installed_modules=("fixture",),
    )

    assert any(error.code == "symlink_escape" for error in result.errors)
    assert all(not path.endswith("escape.py") for path in extractor.paths)

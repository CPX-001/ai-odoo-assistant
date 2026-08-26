import pytest
from odoo_ai.adapters import SOURCE_FIND_MODEL_EXTENSIONS, SOURCE_FIND_SYMBOL, SOURCE_READ_EXCERPT, SourceToolBackend, build_source_tool_registry, source_tool_specs
from odoo_ai.contracts import FindModelExtensionsRequest, FindModelExtensionsResult, FindSymbolRequest, FindSymbolResult, ReadExcerptRequest, SourceExcerpt, ToolSpec
from odoo_ai.tools import ToolExecutorError


class EmptySourceBackend(SourceToolBackend):
    async def find_symbol(self, request: FindSymbolRequest) -> FindSymbolResult:
        return FindSymbolResult(candidates=())

    async def find_model_extensions(self, request: FindModelExtensionsRequest) -> FindModelExtensionsResult:
        return FindModelExtensionsResult(model=request.model, groups=())

    async def read_excerpt(self, request: ReadExcerptRequest) -> SourceExcerpt:
        raise AssertionError("read_excerpt should not run in these catalog tests")


def test_source_tool_specs_are_fixed_and_path_free() -> None:
    specs = {spec.name: spec for spec in source_tool_specs()}
    assert set(specs) == {SOURCE_FIND_MODEL_EXTENSIONS, SOURCE_FIND_SYMBOL, SOURCE_READ_EXCERPT}
    assert specs[SOURCE_FIND_SYMBOL].input_schema == FindSymbolRequest.model_json_schema()
    assert specs[SOURCE_FIND_MODEL_EXTENSIONS].input_schema == FindModelExtensionsRequest.model_json_schema()
    assert specs[SOURCE_READ_EXCERPT].input_schema == ReadExcerptRequest.model_json_schema()
    for spec in specs.values():
        assert "path" not in spec.input_schema.get("properties", {})


def test_source_registry_rejects_unknown_tampered_and_duplicate_specs() -> None:
    backend = EmptySourceBackend()
    canonical = source_tool_specs()[0]
    unknown = ToolSpec.model_validate({**canonical.model_dump(mode="json"), "name": "source.shell", "executor_id": "source.shell.v1"})
    with pytest.raises(ToolExecutorError, match="source_tool_not_allowlisted"):
        build_source_tool_registry(backend, [unknown])
    tampered = ToolSpec.model_validate({**canonical.model_dump(mode="json"), "description": "Run shell"})
    with pytest.raises(ToolExecutorError, match="source_tool_spec_mismatch"):
        build_source_tool_registry(backend, [tampered])
    with pytest.raises(ToolExecutorError, match="source_tool_duplicate"):
        build_source_tool_registry(backend, [canonical, canonical])


def test_source_registry_contains_only_the_advertised_subset() -> None:
    backend = EmptySourceBackend()
    registry = build_source_tool_registry(backend, source_tool_specs()[:1])
    assert [spec.name for spec in registry.specs] == [SOURCE_FIND_SYMBOL]

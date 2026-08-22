"""Bounded, provider-neutral navigation metadata visible to one Odoo user."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ModelName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")]
Label = Annotated[str, Field(min_length=1, max_length=256)]
PositiveId = Annotated[int, Field(strict=True, gt=0)]


class NavigationActionType(StrEnum):
    """Action types safe to describe without executing or evaluating payloads."""

    WINDOW = "ir.actions.act_window"


class NavigationViewMode(StrEnum):
    """Bounded view modes that are useful as HOW_TO metadata."""

    ACTIVITY = "activity"
    CALENDAR = "calendar"
    FORM = "form"
    GRAPH = "graph"
    KANBAN = "kanban"
    LIST = "list"
    PIVOT = "pivot"


class NavigationActionSummary(BaseModel):
    """Safe subset of one visible window action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action_type: NavigationActionType
    target_model: ModelName | None = None
    view_modes: tuple[NavigationViewMode, ...] = Field(default=(), max_length=7)

    @model_validator(mode="after")
    def validate_unique_modes(self) -> Self:
        if len(self.view_modes) != len(set(self.view_modes)):
            raise ValueError("navigation view modes must be unique")
        if (self.target_model is None) != (not self.view_modes):
            raise ValueError("navigation target model and view modes must be present together")
        return self


class NavigationNode(BaseModel):
    """One visible logical menu path, treated as untrusted display data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    menu_id: PositiveId
    label: Label
    parent_id: PositiveId | None = None
    path: tuple[Label, ...] = Field(min_length=1, max_length=8)
    sequence: Annotated[int, Field(strict=True, ge=-2_147_483_648, le=2_147_483_647)] | None
    action: NavigationActionSummary | None = None

    @model_validator(mode="after")
    def validate_path_label(self) -> Self:
        if self.path[-1] != self.label:
            raise ValueError("navigation path must end in its node label")
        return self


class NavigationLimits(BaseModel):
    """Server-side limits applied while collecting visible navigation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_depth: Annotated[int, Field(strict=True, ge=1, le=8)]
    max_nodes: Annotated[int, Field(strict=True, ge=1, le=256)]
    max_bytes: Annotated[int, Field(strict=True, ge=512, le=131_072)]


class NavigationSnapshot(BaseModel):
    """Visible menu tree flattened into deterministic, citable logical paths."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    captured_at: AwareDatetime
    nodes: tuple[NavigationNode, ...] = Field(max_length=256)
    limits: NavigationLimits
    truncated: bool
    content_trust: Literal["untrusted"] = "untrusted"

    @model_validator(mode="after")
    def validate_tree(self) -> Self:
        if len(self.nodes) > self.limits.max_nodes:
            raise ValueError("navigation node limit exceeded")
        by_id = {node.menu_id: node for node in self.nodes}
        if len(by_id) != len(self.nodes):
            raise ValueError("duplicate navigation node")
        for node in self.nodes:
            if len(node.path) > self.limits.max_depth:
                raise ValueError("navigation depth limit exceeded")
            if node.parent_id is None:
                if len(node.path) != 1:
                    raise ValueError("root navigation path is inconsistent")
                continue
            parent = by_id.get(node.parent_id)
            if parent is None or node.path[:-1] != parent.path:
                raise ValueError("navigation parent path is inconsistent")
        return self

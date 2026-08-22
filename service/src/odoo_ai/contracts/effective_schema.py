"""Provider-neutral effective runtime schema contracts for one Odoo user."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

TechnicalName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")]
ModelName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")]
ShortText = Annotated[str, Field(min_length=1, max_length=256)]
Revision = Annotated[str, Field(min_length=1, max_length=128)]


class EffectiveSelectionOption(BaseModel):
    """One normalized runtime selection value and its translated label."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: ShortText
    label: ShortText


class EffectiveFieldSchema(BaseModel):
    """One field visible to the effective Odoo user and allowed by policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: TechnicalName
    label: ShortText | None = None
    field_type: TechnicalName
    relation: ModelName | None = None
    required: bool
    readonly: bool
    searchable: bool
    sortable: bool
    groupable: bool
    selection: tuple[EffectiveSelectionOption, ...] | None = None


class EffectiveModelSchema(BaseModel):
    """The sole field authority exposed for a model during one bounded turn."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_id: Revision
    model: ModelName
    label: ShortText | None = None
    revision: Revision
    fields: dict[TechnicalName, EffectiveFieldSchema]
    source: Literal["runtime"] = "runtime"
    captured_for_user: Annotated[int, Field(strict=True, gt=0)]
    policy_revision: Revision
    captured_at: AwareDatetime

    @model_validator(mode="after")
    def validate_field_mapping(self) -> "EffectiveModelSchema":
        if not self.fields:
            raise ValueError("effective schema must contain fields")
        if any(name != field.name for name, field in self.fields.items()):
            raise ValueError("effective schema field keys must match field names")
        if tuple(self.fields) != tuple(sorted(self.fields)):
            raise ValueError("effective schema fields must be deterministically ordered")
        return self

    @property
    def observed_at(self) -> datetime:
        """Expose the validated aware capture time without provider coupling."""

        return self.captured_at

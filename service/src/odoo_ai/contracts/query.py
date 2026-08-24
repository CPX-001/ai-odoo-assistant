"""Structured, bounded contracts for read-only Odoo QUERY operations."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

TechnicalName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")]
ModelName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")]
SchemaId = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
PositiveId = Annotated[int, Field(strict=True, gt=0)]


class AgentModelSearchRequest(BaseModel):
    """Bounded runtime lookup over installed, user-readable business models."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    query: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=20, strict=True, ge=1, le=32)


class AgentModelCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model: ModelName
    label: str = Field(min_length=1, max_length=240)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("model label is not normalized")
        return value


class AgentModelSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    models: tuple[AgentModelCatalogItem, ...] = Field(max_length=32)
    captured_at: AwareDatetime
    content_trust: Literal["untrusted"] = "untrusted"


class QueryMatch(StrEnum):
    """The only supported condition combinators; nesting is deliberately absent."""

    ALL = "all"
    ANY = "any"


class QueryOperator(StrEnum):
    """Provider-neutral operators translated to ORM only after policy validation."""

    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"


class QuerySortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class QueryAggregateOperation(StrEnum):
    COUNT = "count"
    SUM = "sum"
    MIN = "min"
    MAX = "max"


class QueryCondition(BaseModel):
    """One non-executable filter condition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: TechnicalName
    operator: QueryOperator
    value: JsonValue


class QueryFilter(BaseModel):
    """A flat, bounded conjunction or disjunction of conditions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    match: QueryMatch = QueryMatch.ALL
    conditions: tuple[QueryCondition, ...] = Field(default=(), max_length=8)


class QuerySort(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: TechnicalName
    direction: QuerySortDirection = QuerySortDirection.ASC


class QueryRecordsRequest(BaseModel):
    """Bounded search/read request validated against one effective schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: ModelName
    schema_id: SchemaId
    fields: tuple[TechnicalName, ...] = Field(min_length=1, max_length=16)
    filter: QueryFilter = Field(default_factory=QueryFilter)
    order: tuple[QuerySort, ...] = Field(default=(), max_length=3)
    limit: Annotated[int, Field(strict=True, ge=1, le=50)] = 20

    @model_validator(mode="after")
    def validate_unique_fields(self) -> Self:
        if len(self.fields) != len(set(self.fields)):
            raise ValueError("query fields must be unique")
        order_fields = tuple(item.field for item in self.order)
        if len(order_fields) != len(set(order_fields)):
            raise ValueError("query sort fields must be unique")
        return self


class QueryMetric(BaseModel):
    """One allowlisted aggregate; count applies to records and has no field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: QueryAggregateOperation
    field: TechnicalName | None = None

    @model_validator(mode="after")
    def validate_metric_shape(self) -> Self:
        if (self.operation is QueryAggregateOperation.COUNT) != (self.field is None):
            raise ValueError("count has no field; other aggregates require one field")
        return self


class AggregateRecordsRequest(BaseModel):
    """Bounded aggregate request with optional, non-temporal grouping."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: ModelName
    schema_id: SchemaId
    filter: QueryFilter = Field(default_factory=QueryFilter)
    metrics: tuple[QueryMetric, ...] = Field(min_length=1, max_length=8)
    group_by: tuple[TechnicalName, ...] = Field(default=(), max_length=2)
    group_limit: Annotated[int, Field(strict=True, ge=1, le=50)] = 20

    @model_validator(mode="after")
    def validate_unique_items(self) -> Self:
        if len(self.group_by) != len(set(self.group_by)):
            raise ValueError("group-by fields must be unique")
        identities = tuple((metric.operation, metric.field) for metric in self.metrics)
        if len(identities) != len(set(identities)):
            raise ValueError("aggregate metrics must be unique")
        return self


class QueryRecord(BaseModel):
    """One normalized record returned by a bounded query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: PositiveId
    fields: dict[TechnicalName, JsonValue]


class QueryRecordsResult(BaseModel):
    """Checked search result with enough limit metadata to interpret truncation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: ModelName
    schema_id: SchemaId
    query: QueryRecordsRequest
    records: tuple[QueryRecord, ...] = Field(max_length=50)
    returned_count: Annotated[int, Field(strict=True, ge=0, le=50)]
    limit: Annotated[int, Field(strict=True, ge=1, le=50)]
    truncated: bool
    captured_at: AwareDatetime
    content_trust: Literal["untrusted"] = "untrusted"

    @model_validator(mode="after")
    def validate_result_shape(self) -> Self:
        if (
            self.query.model != self.model
            or self.query.schema_id != self.schema_id
            or self.query.limit != self.limit
            or self.returned_count != len(self.records)
            or len(self.records) > self.limit
        ):
            raise ValueError("query result does not match its canonical request")
        expected_fields = set(self.query.fields)
        if any(set(record.fields) != expected_fields for record in self.records):
            raise ValueError("query record fields do not match the request")
        if len({record.id for record in self.records}) != len(self.records):
            raise ValueError("query records must be unique")
        return self


class AggregateValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: QueryAggregateOperation
    field: TechnicalName | None = None
    value: JsonValue

    @model_validator(mode="after")
    def validate_metric_shape(self) -> Self:
        if (self.operation is QueryAggregateOperation.COUNT) != (self.field is None):
            raise ValueError("aggregate result metric shape is invalid")
        return self


class AggregateGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    group: dict[TechnicalName, JsonValue]
    metrics: tuple[AggregateValue, ...] = Field(min_length=1, max_length=8)


class AggregateRecordsResult(BaseModel):
    """Checked aggregate rows; an ungrouped empty query still returns count zero."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: ModelName
    schema_id: SchemaId
    query: AggregateRecordsRequest
    groups: tuple[AggregateGroup, ...] = Field(max_length=50)
    returned_group_count: Annotated[int, Field(strict=True, ge=0, le=50)]
    group_limit: Annotated[int, Field(strict=True, ge=1, le=50)]
    truncated: bool
    captured_at: AwareDatetime
    content_trust: Literal["untrusted"] = "untrusted"

    @model_validator(mode="after")
    def validate_result_shape(self) -> Self:
        if (
            self.query.model != self.model
            or self.query.schema_id != self.schema_id
            or self.query.group_limit != self.group_limit
            or self.returned_group_count != len(self.groups)
            or len(self.groups) > self.group_limit
        ):
            raise ValueError("aggregate result does not match its canonical request")
        expected_group = set(self.query.group_by)
        expected_metrics = tuple((metric.operation, metric.field) for metric in self.query.metrics)
        for group in self.groups:
            if set(group.group) != expected_group:
                raise ValueError("aggregate group fields do not match the request")
            if (
                tuple((metric.operation, metric.field) for metric in group.metrics)
                != expected_metrics
            ):
                raise ValueError("aggregate metrics do not match the request")
        return self

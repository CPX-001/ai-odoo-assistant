"""Browser-provided navigation context without trusted user identity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ScreenContext(BaseModel):
    """Serializable navigation hints captured by the Odoo UI."""

    model_config = ConfigDict(extra="forbid")

    action_id: int | None = None
    menu_id: int | None = None
    view_type: str | None = None
    model: str | None = None
    res_id: int | None = None
    selected_ids: list[int] = Field(default_factory=list)
    allowed_context_subset: dict[str, JsonValue] = Field(default_factory=dict)
    captured_at: datetime

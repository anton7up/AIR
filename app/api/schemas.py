from typing import Any, Literal

from pydantic import BaseModel, Field


class ProgramStepStateRequest(BaseModel):
    step_id: str
    value: Any = None


class DesireLogRequest(BaseModel):
    intensity: int = Field(ge=1, le=10)
    trigger_id: str | None = None
    emotion: str | None = None
    note: str | None = Field(default=None, max_length=2000)


class SosStartRequest(BaseModel):
    intensity_before: int = Field(ge=1, le=10)
    trigger_id: str | None = None
    reason_response_id: int | None = Field(default=None, ge=1)


class SosCompleteRequest(BaseModel):
    intensity_after: int = Field(ge=1, le=10)
    nicotine_used_after: bool | None = None


class SosActionRequest(BaseModel):
    support_type: Literal[
        "breathing",
        "distraction",
        "change_activity",
        "replacement_action",
        "motivation",
        "personal_plan",
        "ai_support",
    ]
    support_action: str | None = None
    user_response_id: int | None = Field(default=None, ge=1)


class UserResponseRequest(BaseModel):
    response_type: Literal[
        "trigger", "reason", "coping_action", "replacement", "motivation",
        "plan_action", "reflection", "social_response", "lapse_plan", "general",
    ]
    value: str = Field(min_length=1, max_length=500)
    context_id: str | None = Field(default=None, max_length=100)
    parent_response_id: int | None = Field(default=None, ge=1)
    focus: Literal["mouth", "hands", "both"] | None = None


class SosActionCompleteRequest(BaseModel):
    intensity_after: int | None = Field(default=None, ge=1, le=10)
    metadata: dict[str, Any] | None = None


class SosGameResultRequest(BaseModel):
    height: int = Field(ge=0)
    jumps: int = Field(ge=0)
    duration_seconds: int = Field(ge=0)
    boosts_used: int = Field(default=0, ge=0)


class SosTriggerUpdateRequest(BaseModel):
    trigger_id: str | None = Field(default=None, max_length=100)
    action_id: int | None = None


class MotivationRequest(BaseModel):
    motivation: str = Field(min_length=1, max_length=500)


class LapseRequest(BaseModel):
    lapse_type: Literal["single", "multiple", "regular"]
    trigger_id: str | None = None
    note: str | None = Field(default=None, max_length=2000)

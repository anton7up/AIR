import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def validate_bounded_json(
    value: Any,
    *,
    max_bytes: int,
    max_depth: int,
    max_items: int,
) -> Any:
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > max_bytes:
        raise ValueError("Данные слишком большие")

    def visit(item: Any, depth: int) -> None:
        if depth > max_depth:
            raise ValueError("Данные имеют слишком большую вложенность")
        if isinstance(item, dict):
            if len(item) > max_items:
                raise ValueError("Слишком много элементов")
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 100:
                    raise ValueError("Некорректный ключ данных")
                visit(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > max_items:
                raise ValueError("Слишком много элементов")
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, str) and len(item) > 2000:
            raise ValueError("Текстовое значение слишком длинное")
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError("Некорректный тип данных")

    visit(value, 0)
    return value


class ProgramStepStateRequest(BaseModel):
    step_id: str = Field(min_length=1, max_length=100)
    value: Any = None

    @field_validator("value")
    @classmethod
    def bounded_value(cls, value: Any) -> Any:
        return validate_bounded_json(
            value, max_bytes=32_768, max_depth=8, max_items=100
        )


class DesireLogRequest(BaseModel):
    intensity: int = Field(ge=1, le=10)
    trigger_id: str | None = Field(default=None, max_length=100)
    emotion: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=2000)


class SosStartRequest(BaseModel):
    intensity_before: int = Field(ge=1, le=10)
    trigger_id: str | None = Field(default=None, max_length=100)
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
    support_action: str | None = Field(default=None, max_length=100)
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

    @field_validator("metadata")
    @classmethod
    def bounded_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_bounded_json(
            value, max_bytes=8192, max_depth=4, max_items=50
        )


class SosGameResultRequest(BaseModel):
    height: int = Field(ge=0, le=10_000_000)
    jumps: int = Field(ge=0, le=1_000_000)
    duration_seconds: int = Field(ge=0, le=86_400)
    boosts_used: int = Field(default=0, ge=0, le=1_000_000)


class SosTriggerUpdateRequest(BaseModel):
    trigger_id: str | None = Field(default=None, max_length=100)
    action_id: int | None = Field(default=None, ge=1)


class MotivationRequest(BaseModel):
    motivation: str = Field(min_length=1, max_length=500)


class LapseRequest(BaseModel):
    lapse_type: Literal["single", "multiple", "regular"]
    trigger_id: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=2000)

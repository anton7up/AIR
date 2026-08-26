from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class InputType(StrEnum):
    CHOICE = "choice"
    NUMBER = "number"


@dataclass(frozen=True)
class Option:
    label: str
    value: Any


@dataclass(frozen=True)
class Question:
    key: str
    text: str
    input_type: InputType
    options: tuple[Option, ...] = ()
    next_key: str | None = None
    transitions: dict[Any, str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    error_text: str = "Введи число цифрами, пожалуйста."


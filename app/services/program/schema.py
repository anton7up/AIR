from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StepOption:
    id: str
    label: str


@dataclass(frozen=True)
class ProgramStep:
    id: str
    type: str
    title: str
    body: str = ""
    options: tuple[StepOption, ...] = ()
    required: bool = False
    max_selections: int | None = None
    options_source: str | None = None
    button_text: str = "Продолжить"
    content: dict[str, Any] = field(default_factory=dict)
    personalization_key: str | None = None
    branches: dict[str, str] = field(default_factory=dict)
    next_step_id: str | None = None


@dataclass(frozen=True)
class ProgramDay:
    number: int
    title: str
    short_description: str
    steps: tuple[ProgramStep, ...] = field(default_factory=tuple)
    achievement: str | None = None
    task_title: str | None = None
    task_description: str | None = None
    evidence_category: str = "behavioural support"
    evidence_notes: str = "Практическое самонаблюдение и планирование поведения."

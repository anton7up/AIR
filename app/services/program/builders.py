from collections.abc import Iterable

from app.services.program.schema import ProgramDay, ProgramStep, StepOption


def options(*items: tuple[str, str]) -> tuple[StepOption, ...]:
    return tuple(StepOption(option_id, label) for option_id, label in items)


def standard_day(
    *,
    number: int,
    title: str,
    short_description: str,
    intro: str,
    theory_title: str,
    theory: str,
    personalization_key: str,
    personalization_title: str,
    interactive: ProgramStep,
    practice_title: str,
    practice: str,
    summary: str,
    next_teaser: str,
    evidence_category: str,
    evidence_notes: str,
    extra_steps: Iterable[ProgramStep] = (),
) -> ProgramDay:
    steps = (
        ProgramStep(f"d{number}_intro", "info", title, intro),
        ProgramStep(
            f"d{number}_theory",
            "theory",
            theory_title,
            f"{theory}\n\nПрактический смысл сегодняшнего шага: {summary}",
            content={"highlight": summary},
        ),
        ProgramStep(
            f"d{number}_personal",
            "personalized_insight",
            personalization_title,
            personalization_key=personalization_key,
        ),
        interactive,
        *tuple(extra_steps),
        ProgramStep(
            f"d{number}_practice",
            "task",
            practice_title,
            practice,
        ),
        ProgramStep(
            f"d{number}_summary",
            "info",
            "Короткий итог",
            summary,
        ),
        ProgramStep(
            f"d{number}_completion",
            "completion",
            f"День {number} завершён",
            f"{summary}\n\nЗавтра: {next_teaser}",
            options=(StepOption("achievement", f"День {number} пройден"),),
            button_text=f"Завершить День {number}",
        ),
    )
    return ProgramDay(
        number=number,
        title=title,
        short_description=short_description,
        steps=steps,
        task_title=practice_title,
        task_description=practice,
        evidence_category=evidence_category,
        evidence_notes=evidence_notes,
    )


def checkpoint_day(
    *,
    number: int,
    title: str,
    short_description: str,
    intro: str,
    theory: str,
    checkpoint_key: str,
    reflection_prompt: str,
    summary: str,
    next_teaser: str,
    evidence_notes: str,
) -> ProgramDay:
    return ProgramDay(
        number=number,
        title=title,
        short_description=short_description,
        task_title="Один честный вывод",
        task_description=reflection_prompt,
        evidence_category="feedback and self-monitoring",
        evidence_notes=evidence_notes,
        steps=(
            ProgramStep(f"d{number}_intro", "info", title, intro),
            ProgramStep(
                f"d{number}_theory",
                "theory",
                "Смотрим на тенденцию, а не на один момент",
                theory,
                content={"highlight": summary},
            ),
            ProgramStep(
                f"d{number}_checkpoint",
                "checkpoint",
                "Твои данные на сегодня",
                personalization_key=checkpoint_key,
            ),
            ProgramStep(
                f"d{number}_reflection",
                "text",
                reflection_prompt,
                required=True,
                content={"placeholder": "Напиши так, как видишь это сейчас"},
            ),
            ProgramStep(f"d{number}_summary", "info", "Короткий итог", summary),
            ProgramStep(
                f"d{number}_completion",
                "completion",
                f"День {number} завершён",
                f"{summary}\n\nЗавтра: {next_teaser}",
                options=(StepOption("achievement", f"Контрольная точка {number}/30"),),
                button_text=f"Завершить День {number}",
            ),
        ),
    )

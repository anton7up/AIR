from typing import Any

from app.onboarding.config import FIRST_QUESTION_KEY, QUESTIONS
from app.onboarding.schema import InputType, Question


class InvalidAnswer(ValueError):
    pass


class OnboardingEngine:
    def first_question(self) -> Question:
        return QUESTIONS[FIRST_QUESTION_KEY]

    def question(self, key: str) -> Question:
        return QUESTIONS[key]

    def parse_text_answer(self, question: Question, text: str) -> float:
        if question.input_type is not InputType.NUMBER:
            raise InvalidAnswer("This question does not accept text")
        try:
            value = float(text.strip().replace(",", "."))
        except (TypeError, ValueError) as exc:
            raise InvalidAnswer(question.error_text) from exc
        if question.minimum is not None and value < question.minimum:
            raise InvalidAnswer(f"Введи значение не меньше {question.minimum:g}.")
        if question.maximum is not None and value > question.maximum:
            raise InvalidAnswer(f"Введи значение не больше {question.maximum:g}.")
        return value

    def choice_answer(self, question: Question, option_index: int) -> Any:
        try:
            return question.options[option_index].value
        except IndexError as exc:
            raise InvalidAnswer("Такого варианта ответа нет.") from exc

    def next_question(self, question: Question, answer: Any) -> Question | None:
        next_key = (
            question.transitions.get(answer)
            if question.transitions is not None
            else question.next_key
        )
        return QUESTIONS[next_key] if next_key else None


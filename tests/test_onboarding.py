import pytest

from app.onboarding.engine import InvalidAnswer, OnboardingEngine


def test_nicotine_choice_routes_to_correct_branch() -> None:
    engine = OnboardingEngine()
    question = engine.question("nicotine_type")

    assert engine.next_question(question, "cigarettes").key == "cig_daily"
    assert engine.next_question(question, "vape").key == "vape_daily_ml"
    assert engine.next_question(question, "hookah").key == "hookah_weekly_sessions"


def test_number_parser_accepts_decimal_comma() -> None:
    engine = OnboardingEngine()
    assert engine.parse_text_answer(engine.question("vape_daily_ml"), "2,5") == 2.5


def test_number_parser_validates_range() -> None:
    engine = OnboardingEngine()
    with pytest.raises(InvalidAnswer):
        engine.parse_text_answer(engine.question("cig_daily"), "0")


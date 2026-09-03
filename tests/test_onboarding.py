import pytest

from app.onboarding.engine import InvalidAnswer, OnboardingEngine


def test_nicotine_choice_routes_to_correct_branch() -> None:
    engine = OnboardingEngine()
    question = engine.question("nicotine_type")

    assert engine.next_question(question, "cigarettes").key == "cig_daily"
    assert engine.next_question(question, "disposable_e_cigarette").key == "disposable_days_per_device"
    assert engine.next_question(question, "vape").key == "vape_daily_ml"
    assert engine.next_question(question, "hookah").key == "hookah_weekly_sessions"


def test_nicotine_choices_separate_vape_and_disposable_without_emoji() -> None:
    question = OnboardingEngine().question("nicotine_type")

    assert [option.label for option in question.options] == [
        "Сигареты",
        "Одноразовые электронные сигареты",
        "Вейп",
        "IQOS / glo",
        "Снюс",
        "Кальян",
    ]
    assert [option.value for option in question.options] == [
        "cigarettes",
        "disposable_e_cigarette",
        "vape",
        "heated_tobacco",
        "snus",
        "hookah",
    ]


def test_number_parser_accepts_decimal_comma() -> None:
    engine = OnboardingEngine()
    assert engine.parse_text_answer(engine.question("vape_daily_ml"), "2,5") == 2.5


def test_disposable_branch_collects_tenure_before_source() -> None:
    engine = OnboardingEngine()
    price_question = engine.question("disposable_device_price")
    years_question = engine.next_question(price_question, 1000)

    assert years_question is not None
    assert years_question.key == "disposable_years"
    assert engine.next_question(years_question, 4).key == "acquisition_source"


def test_number_parser_validates_range() -> None:
    engine = OnboardingEngine()
    with pytest.raises(InvalidAnswer):
        engine.parse_text_answer(engine.question("cig_daily"), "0")

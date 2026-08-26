from app.services.program.labels import format_program_value, resolve_user_facing_value


def test_custom_sentinels_never_reach_user_facing_text() -> None:
    for sentinel in (
        "custom",
        "other",
        "user_defined",
        "own",
        "other_option",
        "custom_value",
    ):
        assert resolve_user_facing_value(sentinel) == "Свой вариант"


def test_current_and_legacy_custom_shapes_prefer_user_text() -> None:
    assert format_program_value({"value": "custom", "custom_text": "Выйду на воздух"}) == "Выйду на воздух"
    assert format_program_value({"main_reason": "custom", "main_reason_custom": "Хочу свободы"}) == "Хочу свободы"
    assert resolve_user_facing_value("custom:Позвоню другу") == "Позвоню другу"


def test_unknown_internal_identifier_has_safe_fallback() -> None:
    rendered = format_program_value("unknown_internal_value")
    assert rendered == "Сохранённый вариант"
    assert "unknown_internal_value" not in rendered

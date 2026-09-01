from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import TelegramIdentity, get_telegram_identity
from app.api.schemas import (
    DesireLogRequest,
    LapseRequest,
    MotivationRequest,
    ProgramStepStateRequest,
    SosActionCompleteRequest,
    SosActionRequest,
    SosCompleteRequest,
    SosGameResultRequest,
    SosStartRequest,
    SosTriggerUpdateRequest,
    UserResponseRequest,
)
from app.core.config import Settings, get_settings
from app.db.models import (
    DevProgramDayState,
    LapseType,
    NicotineDesireLog,
    ProgramDayCompletion,
    ProgramDayState,
    QuitAttempt,
    SmokingProfile,
    SosAction,
    SosSession,
    Subscription,
    SubscriptionStatus,
    User,
    UserResponse,
    UserResponseType,
)
from app.db.session import get_session
from app.services.consent import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    PERSONAL_DATA_CONSENT_PATH,
    accept_personal_data_consent,
    find_telegram_user,
    get_or_create_telegram_user,
    has_current_personal_data_consent,
    require_current_personal_data_consent,
)
from app.services.program.content import (
    EMOTIONS,
    PROGRAM_DAYS,
    PROGRAM_LENGTH,
    QUIT_REASONS,
    REASON_MOTIVATION,
    TRIGGER_OPTIONS,
)
from app.services.program.engine import ProgramValidationError, program_engine
from app.services.program.personal_plan import build_personal_plan
from app.services.progress import ProgressCalculator, nearest_recovery, recovery_timeline
from app.services.quit_attempts import quit_attempt_service
from app.services.support import SupportValidationError, support_service
from app.services.user_responses import ACTION_TYPES, user_response_memory

router = APIRouter(prefix="/api/v1/mini-app", tags=["mini-app"])
progress_calculator = ProgressCalculator()


async def load_user(session: AsyncSession, telegram_id: int) -> tuple[User, SmokingProfile]:
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сначала заверши знакомство с AIR в боте")
    profile = await session.scalar(select(SmokingProfile).where(SmokingProfile.user_id == user.id))
    if profile is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Профиль употребления заполнен не полностью")
    return user, profile


async def access_status(
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    include_tester: bool = True,
) -> tuple[str, Subscription | None]:
    # Developer access is derived only from the already authenticated Telegram user.
    # It is intentionally virtual: no Subscription or payment-like record is created.
    if settings.is_program_dev(user.telegram_id):
        return "active", None
    # Closed-beta access is also virtual and derives only from authenticated Telegram identity.
    if include_tester and settings.is_tester(user.telegram_id):
        return "active", None
    subscription = await session.scalar(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.id.desc())
    )
    if subscription is None:
        return "free", None
    now = datetime.now(timezone.utc)
    ends_at = subscription.ends_at
    if ends_at is not None and ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    if subscription.status == SubscriptionStatus.ACTIVE and ends_at and ends_at <= now:
        subscription.status = SubscriptionStatus.EXPIRED
        await session.commit()
    if subscription.status == SubscriptionStatus.ACTIVE:
        return "active", subscription
    if subscription.status == SubscriptionStatus.EXPIRED:
        return "expired", subscription
    return "free", subscription


def access_plan(
    user: User,
    settings: Settings,
    subscription: Subscription | None,
    *,
    include_tester: bool = True,
) -> str:
    if settings.is_program_dev(user.telegram_id):
        return "developer"
    if include_tester and settings.is_tester(user.telegram_id):
        return "tester"
    return subscription.plan if subscription else "free"


async def access_payload(
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    include_tester: bool,
) -> dict[str, object]:
    access, subscription = await access_status(
        session, user, settings, include_tester=include_tester
    )
    return {
        "status": access,
        "plan": access_plan(
            user, settings, subscription, include_tester=include_tester
        ),
        "ends_at": subscription.ends_at if subscription else None,
        "development_activation_available": settings.development_access_enabled,
        "receipt_email": user.receipt_email,
        "is_admin": settings.is_admin(user.telegram_id),
        "links": {
            "support": settings.support_url,
            "terms": settings.terms_url,
            "privacy": settings.privacy_url,
        },
    }


async def require_active(
    identity: TelegramIdentity = Depends(get_telegram_identity),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> tuple[User, SmokingProfile, AsyncSession]:
    user, profile = await load_user(session, identity.telegram_id)
    access, _ = await access_status(session, user, settings)
    if access != "active":
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Доступ к AIR сейчас не активен")
    return user, profile, session


async def require_active_consent(
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active),
) -> tuple[User, SmokingProfile, AsyncSession]:
    user, _, _ = context
    require_current_personal_data_consent(user)
    return context


async def require_program_dev(
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
    settings: Settings = Depends(get_settings),
) -> tuple[User, SmokingProfile, AsyncSession]:
    user, _, _ = context
    if not settings.is_program_dev(user.telegram_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Режим предпросмотра программы недоступен")
    return context


def consent_payload(user: User | None) -> dict[str, object]:
    if user is None or not has_current_personal_data_consent(user):
        return {
            "accepted": False,
            "required_version": CURRENT_PERSONAL_DATA_CONSENT_VERSION,
            "consent_version": None,
            "consent_at": None,
            "document_url": PERSONAL_DATA_CONSENT_PATH,
        }
    consent_at = user.personal_data_consent_at
    if consent_at is not None and consent_at.tzinfo is None:
        consent_at = consent_at.replace(tzinfo=timezone.utc)
    return {
        "accepted": True,
        "required_version": CURRENT_PERSONAL_DATA_CONSENT_VERSION,
        "consent_version": user.personal_data_consent_version,
        "consent_at": consent_at,
        "document_url": PERSONAL_DATA_CONSENT_PATH,
    }


@router.get("/consent")
async def get_consent_status(
    identity: TelegramIdentity = Depends(get_telegram_identity),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    user = await find_telegram_user(session, identity.telegram_id)
    return consent_payload(user)


@router.post("/consent/accept")
async def accept_consent(
    identity: TelegramIdentity = Depends(get_telegram_identity),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    user = await get_or_create_telegram_user(
        session,
        telegram_id=identity.telegram_id,
        first_name=identity.first_name,
        username=identity.username,
    )
    await accept_personal_data_consent(session, user)
    await session.commit()
    return consent_payload(user)


@router.get("/access")
async def get_access(
    identity: TelegramIdentity = Depends(get_telegram_identity),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    user, _ = await load_user(session, identity.telegram_id)
    # Tester access is virtual and is resolved from verified Telegram initData on every load.
    return await access_payload(session, user, settings, include_tester=True)


@router.post("/access/refresh")
async def refresh_access(
    identity: TelegramIdentity = Depends(get_telegram_identity),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    user, _ = await load_user(session, identity.telegram_id)
    return await access_payload(session, user, settings, include_tester=True)


@router.post("/dev/activate")
async def activate_development_access(
    identity: TelegramIdentity = Depends(get_telegram_identity),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    if not settings.development_access_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    user, _ = await load_user(session, identity.telegram_id)
    subscription = await session.scalar(
        select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.id.desc())
    )
    now = datetime.now(timezone.utc)
    if subscription is None:
        subscription = Subscription(user_id=user.id, plan="development", status=SubscriptionStatus.ACTIVE)
        session.add(subscription)
    subscription.plan = "development"
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.starts_at = now
    subscription.ends_at = None
    await session.commit()
    return {"status": "active"}


def dashboard_payload(
    user: User,
    profile: SmokingProfile,
    active_attempt: QuitAttempt | None,
) -> dict[str, object]:
    started_at = active_attempt.started_at if active_attempt else None
    snapshot = progress_calculator.calculate(user, profile, started_at)
    return {
        "first_name": user.telegram_first_name,
        "quit_started_at": started_at,
        "elapsed_seconds": snapshot.elapsed_seconds,
        "days": snapshot.days,
        "hours": snapshot.hours,
        "money_saved": snapshot.money_saved,
        "units_avoided": snapshot.units_avoided,
        "unit_label": snapshot.unit_label,
        "program_day": snapshot.program_day,
        "program_length": PROGRAM_LENGTH,
        "recovery": nearest_recovery(snapshot.elapsed_seconds // 3600),
        "has_active_attempt": active_attempt is not None,
    }


def achievement_payload(
    best_streak_seconds: int,
    completed_program_days: set[int],
    sos_count: int,
    desire_count: int,
) -> list[dict[str, object]]:
    return [
        {"id": "first_step", "title": "🏆 День 1 пройден", "unlocked": 1 in completed_program_days},
        {"id": "24h", "title": "⏱ Первые 24 часа", "unlocked": best_streak_seconds >= 86400},
        {"id": "3d", "title": "🌱 3 дня", "unlocked": best_streak_seconds >= 3 * 86400},
        {"id": "7d", "title": "⭐ День 7 пройден", "unlocked": 7 in completed_program_days},
        {"id": "14d", "title": "🏅 День 14 пройден", "unlocked": 14 in completed_program_days},
        {"id": "21d", "title": "🌿 День 21 пройден", "unlocked": 21 in completed_program_days},
        {"id": "30d", "title": "🏆 День 30 пройден", "unlocked": 30 in completed_program_days},
        {"id": "sos", "title": "🆘 Первая SOS-сессия", "unlocked": sos_count >= 1},
        {"id": "three_desires", "title": "📝 Три желания", "unlocked": desire_count >= 3},
    ]


@router.get("/dashboard")
async def dashboard(context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent)) -> dict[str, object]:
    user, profile, session = context
    active_attempt = await quit_attempt_service.current(session, user.id)
    payload = dashboard_payload(user, profile, active_attempt)
    attempt_metrics = await quit_attempt_service.metrics(session, user.id)
    payload["number_of_attempts"] = attempt_metrics.attempts
    current_day = progress_calculator.program_day(user)
    content = PROGRAM_DAYS.get(current_day)
    payload["today_task"] = {
        "day": current_day,
        "title": content.title if content else "Закрепляем новый ритм",
        "description": content.task_description if content else "Выбери один полезный ритуал из предыдущих дней и повтори его сегодня.",
    }
    payload["program_started"] = user.program_started_at is not None
    return payload


@router.get("/program")
async def program(
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    user, profile, session = context
    current_day = progress_calculator.program_day(user)
    is_program_dev = settings.is_program_dev(user.telegram_id)
    completed = set(
        await session.scalars(select(ProgramDayCompletion.day_number).where(ProgramDayCompletion.user_id == user.id))
    )
    days = []
    for number in range(1, PROGRAM_LENGTH + 1):
        day = PROGRAM_DAYS.get(number)
        days.append({
            "number": number,
            "title": day.title if day else "Скоро в AIR",
            "description": day.short_description if day else "Содержание этого дня появится в следующей версии программы.",
            "task": day.task_description if day else "Задание готовится.",
            "status": "completed" if number in completed else "current" if number == current_day else "available" if number < current_day else "locked",
            "completed": number in completed,
            "interactive": day is not None,
            "dev_preview_available": is_program_dev and day is not None,
            "dev_unlocked": is_program_dev and number > current_day,
        })
    responses = list(
        (await session.scalars(select(UserResponse).where(UserResponse.user_id == user.id))).all()
    )
    return {
        "current_day": current_day,
        "total_days": PROGRAM_LENGTH,
        "program_started": user.program_started_at is not None,
        "is_program_dev": is_program_dev,
        "completed_count": len(completed),
        "personal_plan_strategy_count": build_personal_plan(
            list(
                (
                    await session.scalars(
                        select(ProgramDayState).where(ProgramDayState.user_id == user.id)
                    )
                ).all()
            ),
            responses=responses,
        )["strategy_count"],
        "days": days,
    }


@router.post("/program/start")
async def start_program(
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    attempt = await quit_attempt_service.start_program(session, user)
    day = program_engine.get_day(1)
    if day is not None:
        await program_engine.get_or_create_state(session, user.id, day)
        await program_engine.get_or_create_profile(session, user.id)
    await session.commit()
    return {
        "program_started_at": user.program_started_at,
        "quit_attempt_id": attempt.id,
        "quit_started_at": attempt.started_at,
    }


@router.get("/program/{day_number}")
async def program_day(
    day_number: int,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    if day_number > program_engine.current_day(user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Этот день программы пока закрыт")
    try:
        return await program_engine.day_payload(session, user, day_number)
    except ProgramValidationError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/program/{day_number}/state")
async def save_program_day_state(
    day_number: int,
    request: ProgramStepStateRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    if day_number > program_engine.current_day(user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Этот день программы пока закрыт")
    try:
        if day_number == 1 and request.step_id == "start":
            await quit_attempt_service.start_program(session, user)
        await program_engine.save_step(
            session, user, day_number, request.step_id, request.value
        )
        await session.commit()
        return await program_engine.day_payload(session, user, day_number)
    except ProgramValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/program/{day_number}/complete")
async def complete_program_day(day_number: int, context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent)) -> dict[str, object]:
    user, profile, session = context
    current_day = progress_calculator.program_day(user)
    if day_number < 1 or day_number > current_day or day_number > PROGRAM_LENGTH:
        raise HTTPException(status.HTTP_409_CONFLICT, "Этот день программы пока закрыт")
    existing = await session.scalar(
        select(ProgramDayCompletion).where(
            ProgramDayCompletion.user_id == user.id,
            ProgramDayCompletion.day_number == day_number,
        )
    )
    if existing is None:
        session.add(ProgramDayCompletion(user_id=user.id, day_number=day_number))
    state = await session.scalar(
        select(ProgramDayState).where(
            ProgramDayState.user_id == user.id,
            ProgramDayState.day_number == day_number,
        )
    )
    if state is not None:
        day = program_engine.get_day(day_number)
        completion_step = day.steps[-1].id if day else "completion"
        if state.current_step != completion_step and not state.completed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Сначала заверши интерактивную часть дня",
            )
        state.completed = True
    await session.commit()
    return {"day_number": day_number, "completed": True}


@router.post("/program/{day_number}/draft")
async def save_program_day_draft(
    day_number: int,
    request: ProgramStepStateRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    if day_number > program_engine.current_day(user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Этот день программы пока закрыт")
    try:
        await program_engine.save_step_draft(
            session, user, day_number, request.step_id, request.value
        )
        await session.commit()
        return await program_engine.day_payload(session, user, day_number)
    except ProgramValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/dev/program/{day_number}")
async def dev_program_day(
    day_number: int,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_program_dev),
) -> dict[str, object]:
    user, _, session = context
    if day_number < 1 or day_number > PROGRAM_LENGTH:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "День программы не найден")
    try:
        return await program_engine.day_payload(
            session, user, day_number, dev_preview=True
        )
    except ProgramValidationError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/dev/program/{day_number}/state")
async def save_dev_program_day_state(
    day_number: int,
    request: ProgramStepStateRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_program_dev),
) -> dict[str, object]:
    user, _, session = context
    if day_number < 1 or day_number > PROGRAM_LENGTH:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "День программы не найден")
    try:
        await program_engine.save_step(
            session,
            user,
            day_number,
            request.step_id,
            request.value,
            dev_preview=True,
        )
        await session.commit()
        return await program_engine.day_payload(
            session, user, day_number, dev_preview=True
        )
    except ProgramValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/dev/program/{day_number}/complete")
async def complete_dev_program_day(
    day_number: int,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_program_dev),
) -> dict[str, object]:
    user, _, session = context
    day = program_engine.get_day(day_number)
    if day is None or day_number < 1 or day_number > PROGRAM_LENGTH:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "День программы не найден")
    state = await program_engine.get_or_create_state(
        session, user.id, day, dev_preview=True
    )
    completion_step = day.steps[-1].id
    if state.current_step != completion_step and not state.completed:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Сначала заверши интерактивную часть дня"
        )
    state.completed = True
    await session.commit()
    return await program_engine.day_payload(
        session, user, day_number, dev_preview=True
    )


@router.post("/dev/program/{day_number}/draft")
async def save_dev_program_day_draft(
    day_number: int,
    request: ProgramStepStateRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_program_dev),
) -> dict[str, object]:
    user, _, session = context
    if day_number < 1 or day_number > PROGRAM_LENGTH:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "День программы не найден")
    try:
        await program_engine.save_step_draft(
            session,
            user,
            day_number,
            request.step_id,
            request.value,
            dev_preview=True,
        )
        await session.commit()
        return await program_engine.day_payload(
            session, user, day_number, dev_preview=True
        )
    except ProgramValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/dev/program/{day_number}/reset")
async def reset_dev_program_day(
    day_number: int,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_program_dev),
) -> dict[str, object]:
    user, _, session = context
    if day_number < 1 or day_number > PROGRAM_LENGTH:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "День программы не найден")
    await session.execute(
        delete(DevProgramDayState).where(
            DevProgramDayState.user_id == user.id,
            DevProgramDayState.day_number == day_number,
        )
    )
    await session.commit()
    return await program_engine.day_payload(
        session, user, day_number, dev_preview=True
    )


@router.post("/sos/sessions")
async def record_sos_session(exercise: str, context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent)) -> dict[str, object]:
    user, _, session = context
    allowed = {"breathing", "timer", "distraction", "motivation"}
    if exercise not in allowed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Этот инструмент SOS недоступен")
    session.add(SosSession(user_id=user.id, exercise_type=exercise))
    await session.commit()
    return {"recorded": True, "exercise": exercise}


def option_payload(options: tuple) -> list[dict[str, str]]:
    return [{"id": option.id, "label": option.label} for option in options]


@router.get("/support-context")
async def support_context(
    context: tuple[User, SmokingProfile | None, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, smoking_profile, session = context
    profile = await support_service.program_profile(session, user.id)
    primary = list(profile.primary_triggers or []) if profile else []
    all_triggers = option_payload(TRIGGER_OPTIONS)
    trigger_lookup = {item["id"]: item for item in all_triggers}
    ordered = [trigger_lookup[item] for item in primary if item in trigger_lookup]
    ordered.extend(item for item in all_triggers if item["id"] not in primary)
    primary_reason = profile.primary_quit_reason if profile else None
    reason_lookup = {option.id: option.label for option in QUIT_REASONS}
    states = list(
        (
            await session.scalars(
                select(ProgramDayState).where(ProgramDayState.user_id == user.id)
            )
        ).all()
    )
    responses = list(
        (await session.scalars(select(UserResponse).where(UserResponse.user_id == user.id))).all()
    )
    answers: dict[str, object] = {}
    for state in states:
        answers.update(state.state_json or {})
    personal_plan = build_personal_plan(
        states, primary_triggers=primary, responses=responses
    )
    action_labels = {
        "walk": "🚶 Пройтись",
        "walk_3": "🚶 Пройтись 3 минуты",
        "walk_5": "🚶 Пройтись 5 минут",
        "breathing": "🌬 Спокойное дыхание",
        "water": "💧 Выпить воды",
        "change_place": "🚪 Сменить место",
        "music": "🎵 Включить музыку",
        "outside": "🌳 Выйти на воздух",
        "stretch": "🤸 Короткая разминка",
        "stairs": "🪜 Пройти по лестнице",
        "contact": "💬 Связаться с человеком",
        "sos": "🆘 Открыть SOS",
    }

    def plan_action(plan_key: str, field: str | None = None) -> str | None:
        value = answers.get(plan_key)
        if field and isinstance(value, dict):
            selected = value.get(field)
            return selected if isinstance(selected, str) else None
        if isinstance(value, str):
            return value
        if isinstance(value, list) and value and isinstance(value[0], str):
            return value[0]
        return None

    recommendations: dict[str, list[dict[str, str]]] = {}
    recommendation_sources: dict[str, list[tuple[str, str | None]]] = {
        "stress": [("stress_plan", "first_action"), ("trigger_plan", "first_action")],
        "work_study": [("break_replacement", None), ("movement_switch", None)],
        "boredom": [("boredom_menu", "one_minute"), ("movement_switch", None)],
        "after_meal": [("after_meal_plan", "new_action")],
    }
    for trigger_id, sources in recommendation_sources.items():
        for plan_key, plan_field in sources:
            action_id = plan_action(plan_key, plan_field)
            if action_id and action_id in action_labels:
                support_type = (
                    "breathing"
                    if action_id == "breathing"
                    else "motivation"
                    if action_id == "sos"
                    else "change_activity"
                )
                recommendations.setdefault(trigger_id, []).append(
                    {
                        "action_id": action_id,
                        "label": action_labels[action_id],
                        "support_type": support_type,
                        "reason": "Ты раньше выбрал это действие в программе AIR.",
                    }
                )

    habit_loop = answers.get("personal_habit_loop")
    if isinstance(habit_loop, dict):
        loop_trigger = habit_loop.get("trigger")
        loop_action = habit_loop.get("alternative")
        if (
            isinstance(loop_trigger, str)
            and isinstance(loop_action, str)
            and loop_action in action_labels
        ):
            support_type = (
                "breathing"
                if loop_action == "breathing"
                else "motivation"
                if loop_action == "sos"
                else "change_activity"
            )
            recommendations.setdefault(loop_trigger, []).insert(
                0,
                {
                    "action_id": loop_action,
                    "label": action_labels[loop_action],
                    "support_type": support_type,
                    "reason": "Ты выбрал это действие для такой ситуации в Дне 2.",
                },
            )

    primary_trigger = primary[0] if primary else None
    primary_plan_action = plan_action("trigger_plan", "first_action")
    if (
        primary_trigger
        and primary_plan_action
        and primary_plan_action in action_labels
        and not any(
            item["action_id"] == primary_plan_action
            for item in recommendations.get(primary_trigger, [])
        )
    ):
        support_type = (
            "breathing"
            if primary_plan_action == "breathing"
            else "motivation"
            if primary_plan_action == "sos"
            else "change_activity"
        )
        recommendations.setdefault(primary_trigger, []).append(
            {
                "action_id": primary_plan_action,
                "label": action_labels[primary_plan_action],
                "support_type": support_type,
                "reason": "Ты выбрал это действие для главного триггера в Дне 5.",
            }
        )
    analytics = await support_service.tool_analytics(session, user.id)
    game_best_height = await support_service.air_cloud_best_height(session, user.id)
    active_attempt = await quit_attempt_service.current(session, user.id)
    snapshot = (
        progress_calculator.calculate(
            user,
            smoking_profile,
            active_attempt.started_at if active_attempt else None,
        )
        if smoking_profile is not None
        else None
    )
    survived_count = int(
        await session.scalar(
            select(func.count(SosSession.id)).where(
                SosSession.user_id == user.id,
                SosSession.finished_at.is_not(None),
                SosSession.nicotine_used_after.is_(False),
            )
        )
        or 0
    )
    return {
        "triggers": ordered,
        "primary_triggers": primary,
        "emotions": option_payload(EMOTIONS),
        "primary_quit_reason": primary_reason,
        "primary_quit_reason_label": reason_lookup.get(primary_reason or ""),
        "motivation_text": user.motivation
        or REASON_MOTIVATION.get(primary_reason or "", REASON_MOTIVATION["default"]),
        "has_personal_motivation": bool(user.motivation or primary_reason),
        "motivation_stats": {
            "elapsed_seconds": snapshot.elapsed_seconds if snapshot else 0,
            "money_saved": snapshot.money_saved if snapshot else 0,
            "cravings_survived": survived_count,
        },
        "recommendations": recommendations,
        "personal_plan": personal_plan,
        "tool_analytics": analytics,
        "game_best_height": game_best_height,
    }


def response_payload(response: UserResponse) -> dict[str, object]:
    return {
        "id": response.id,
        "value": response.value,
        "response_type": response.response_type.value,
        "context_id": response.context_id,
        "parent_response_id": response.parent_response_id,
        "focus": response.focus,
        "usage_count": response.usage_count,
        "average_effect": round(
            response.effectiveness_sum / response.effectiveness_samples, 2
        ) if response.effectiveness_samples else None,
    }


@router.get("/responses/reasons")
async def remembered_reasons(
    context_id: str | None = None,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    items = await user_response_memory.ranked(
        session,
        user_id=user.id,
        response_types=(UserResponseType.REASON, UserResponseType.TRIGGER),
        context_id=context_id,
        limit=5,
    )
    return {"items": [response_payload(item) for item in items]}


@router.get("/responses/actions")
async def remembered_actions(
    context_id: str | None = None,
    reason_response_id: int | None = None,
    focus: str | None = None,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    if focus not in {None, "mouth", "hands", "both"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестный тип действия")
    items = await user_response_memory.ranked(
        session,
        user_id=user.id,
        response_types=tuple(ACTION_TYPES),
        context_id=context_id,
        parent_response_id=reason_response_id,
        focus=focus,
        limit=8,
    )
    return {"items": [response_payload(item) for item in items]}


@router.post("/responses")
async def remember_response(
    request: UserResponseRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    parent = None
    if request.parent_response_id is not None:
        parent = await user_response_memory.get(session, user.id, request.parent_response_id)
        if parent is None or parent.response_type not in {UserResponseType.REASON, UserResponseType.TRIGGER}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Сохранённая причина не найдена")
    try:
        response = await user_response_memory.remember(
            session,
            user_id=user.id,
            response_type=request.response_type,
            value=request.value,
            source="sos",
            source_ref="sos:user_option",
            context_id=parent.context_id if parent else request.context_id,
            parent_response_id=parent.id if parent else None,
            focus=request.focus,
        )
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return response_payload(response)


@router.patch("/motivation")
async def update_motivation(
    request: MotivationRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, str]:
    user, _, session = context
    try:
        remembered = await user_response_memory.remember(
            session,
            user_id=user.id,
            response_type=UserResponseType.MOTIVATION,
            value=request.motivation,
            source="sos",
            source_ref="sos:motivation",
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    user.motivation = remembered.value
    await session.commit()
    return {"motivation": user.motivation}


@router.post("/nicotine-desire")
async def create_desire_log(
    request: DesireLogRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    try:
        entry = await support_service.log_desire(
            session,
            user,
            request.intensity,
            request.trigger_id,
            request.emotion,
            request.note,
        )
        await session.commit()
    except SupportValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"id": entry.id, "created_at": entry.created_at, "recorded": True}


@router.get("/nicotine-desire/recent")
async def recent_desire_logs(
    limit: int = 10,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    safe_limit = min(50, max(1, limit))
    entries = (
        await session.scalars(
            select(NicotineDesireLog)
            .where(NicotineDesireLog.user_id == user.id)
            .order_by(NicotineDesireLog.created_at.desc())
            .limit(safe_limit)
        )
    ).all()
    return {
        "items": [
            {
                "id": entry.id,
                "intensity": entry.intensity,
                "trigger_id": entry.trigger_id,
                "emotion": entry.emotion,
                "note": entry.note,
                "created_at": entry.created_at,
            }
            for entry in entries
        ]
    }


@router.post("/sos/start")
async def start_sos(
    request: SosStartRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    try:
        entry = await support_service.start_sos(
            session, user, request.intensity_before, request.trigger_id,
            request.reason_response_id,
        )
        await session.commit()
    except SupportValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"id": entry.id, "started_at": entry.started_at}


@router.post("/sos/{session_id}/complete")
async def complete_sos(
    session_id: int,
    request: SosCompleteRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    entry = await session.scalar(
        select(SosSession).where(
            SosSession.id == session_id, SosSession.user_id == user.id
        )
    )
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сессия SOS не найдена")
    try:
        await support_service.finish_sos(
            session, entry, request.intensity_after, request.nicotine_used_after
        )
        await session.commit()
    except SupportValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {
        "id": entry.id,
        "intensity_before": entry.intensity_before,
        "intensity_after": entry.intensity_after,
        "still_strong": bool(entry.intensity_after and entry.intensity_after >= 8),
        "completed": True,
    }


@router.post("/sos/{session_id}/actions")
async def start_sos_action(
    session_id: int,
    request: SosActionRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    entry = await session.scalar(
        select(SosSession).where(
            SosSession.id == session_id, SosSession.user_id == user.id
        )
    )
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сессия SOS не найдена")
    try:
        action = await support_service.start_sos_action(
            session, entry, request.support_type, request.support_action,
            request.user_response_id,
        )
        await session.commit()
    except SupportValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {
        "id": action.id,
        "sequence_number": action.sequence_number,
        "support_type": action.support_type,
        "intensity_before": action.intensity_before,
        "started_at": action.started_at,
    }


@router.post("/sos/{session_id}/actions/{action_id}/complete")
async def complete_sos_action(
    session_id: int,
    action_id: int,
    request: SosActionCompleteRequest | None = None,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    action = await session.scalar(
        select(SosAction)
        .join(SosSession, SosSession.id == SosAction.sos_session_id)
        .where(
            SosAction.id == action_id,
            SosAction.sos_session_id == session_id,
            SosSession.user_id == user.id,
        )
    )
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Действие SOS не найдено")
    await support_service.complete_sos_action(
        session,
        action,
        request.intensity_after if request else None,
        request.metadata if request else None,
    )
    await session.commit()
    return {
        "id": action.id,
        "completed_at": action.completed_at,
        "intensity_before": action.intensity_before,
        "intensity_after": action.intensity_after,
        "effect_delta": action.effect_delta,
    }


@router.post("/sos/{session_id}/actions/{action_id}/game-result")
async def record_sos_game_result(
    session_id: int,
    action_id: int,
    request: SosGameResultRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    action = await session.scalar(
        select(SosAction)
        .join(SosSession, SosSession.id == SosAction.sos_session_id)
        .where(
            SosAction.id == action_id,
            SosAction.sos_session_id == session_id,
            SosSession.user_id == user.id,
        )
    )
    if action is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Действие SOS не найдено")
    try:
        metadata, new_record = await support_service.record_air_cloud_result(
            session,
            action,
            user.id,
            request.height,
            request.jumps,
            request.duration_seconds,
            request.boosts_used,
        )
        await session.commit()
    except SupportValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"metadata": metadata, "new_record": new_record}


@router.patch("/sos/{session_id}/trigger")
async def update_sos_trigger(
    session_id: int,
    request: SosTriggerUpdateRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    entry = await session.scalar(
        select(SosSession).where(
            SosSession.id == session_id, SosSession.user_id == user.id
        )
    )
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сессия SOS не найдена")
    try:
        await support_service.update_sos_trigger(
            session, entry, request.trigger_id, request.action_id
        )
        await session.commit()
    except SupportValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"id": entry.id, "trigger_id": entry.trigger_id}


@router.post("/lapse")
async def register_lapse(
    request: LapseRequest,
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    lapse = await support_service.register_lapse(
        session,
        user,
        LapseType(request.lapse_type),
        request.trigger_id,
        request.note,
    )
    await session.commit()
    return {
        "id": lapse.id,
        "occurred_at": lapse.occurred_at,
        "message": "Это событие не отменяет твой прогресс в программе.",
        "can_restart": True,
    }


@router.get("/quit-attempt/current")
async def current_quit_attempt(
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    attempt = await quit_attempt_service.current(session, user.id)
    metrics = await quit_attempt_service.metrics(session, user.id)
    return {
        "attempt": (
            {
                "id": attempt.id,
                "started_at": attempt.started_at,
                "status": attempt.status.value,
            }
            if attempt
            else None
        ),
        "current_seconds": metrics.current_seconds,
        "best_seconds": metrics.best_seconds,
        "total_seconds": metrics.total_seconds,
        "number_of_attempts": metrics.attempts,
    }


@router.post("/quit-attempt/restart")
async def restart_quit_attempt(
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
) -> dict[str, object]:
    user, _, session = context
    attempt = await quit_attempt_service.restart(session, user)
    await session.commit()
    return {"id": attempt.id, "started_at": attempt.started_at, "status": "active"}


@router.get("/progress")
async def progress(context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent)) -> dict[str, object]:
    user, profile, session = context
    active_attempt = await quit_attempt_service.current(session, user.id)
    snapshot = progress_calculator.calculate(
        user, profile, active_attempt.started_at if active_attempt else None
    )
    completed_day_numbers = set(
        await session.scalars(
            select(ProgramDayCompletion.day_number).where(
                ProgramDayCompletion.user_id == user.id
            )
        )
    )
    completed_days = len(completed_day_numbers)
    sos_count = int(
        await session.scalar(
            select(func.count(SosSession.id)).where(SosSession.user_id == user.id)
        )
        or 0
    )
    desire_count = int(
        await session.scalar(
            select(func.count(NicotineDesireLog.id)).where(
                NicotineDesireLog.user_id == user.id
            )
        )
        or 0
    )
    attempt_metrics = await quit_attempt_service.metrics(session, user.id)
    achievements = achievement_payload(
        attempt_metrics.best_seconds, completed_day_numbers, sos_count, desire_count
    )
    return {
        **dashboard_payload(user, profile, active_attempt),
        "completed_program_days": completed_days,
        "current_streak_seconds": attempt_metrics.current_seconds,
        "best_streak_seconds": attempt_metrics.best_seconds,
        "total_nicotine_free_seconds": attempt_metrics.total_seconds,
        "number_of_attempts": attempt_metrics.attempts,
        "recovery_timeline": recovery_timeline(snapshot.elapsed_seconds // 3600),
        "achievements": achievements,
    }


@router.get("/profile")
async def profile(
    context: tuple[User, SmokingProfile, AsyncSession] = Depends(require_active_consent),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    user, smoking_profile, session = context
    access, subscription = await access_status(session, user, settings)
    active_attempt = await quit_attempt_service.current(session, user.id)
    return {
        "first_name": user.telegram_first_name,
        "username": user.username,
        "nicotine_type": smoking_profile.nicotine_type.value,
        "daily_units": float(Decimal(smoking_profile.daily_units or 0)),
        "unit_label": progress_calculator.calculate(
            user,
            smoking_profile,
            active_attempt.started_at if active_attempt else None,
        ).unit_label,
        "quit_started_at": active_attempt.started_at if active_attempt else None,
        "registered_at": user.registered_at,
        "access_status": access,
        "plan": access_plan(user, settings, subscription),
        "links": {"support": settings.support_url, "terms": settings.terms_url, "privacy": settings.privacy_url},
        "motivation": user.motivation,
    }

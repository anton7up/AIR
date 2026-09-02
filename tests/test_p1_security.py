import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.main import documentation_config
from app.api.mini_app import create_desire_log, register_lapse, start_sos
from app.api.schemas import (
    DesireLogRequest,
    LapseRequest,
    SosActionCompleteRequest,
    SosStartRequest,
)
from app.core.security import ProductionTrustedHostMiddleware, SecurityHeadersMiddleware
from app.db.base import Base
from app.db.models import (
    IdempotencyRecord,
    LapseType,
    NicotineDesireLog,
    NicotineLapse,
    NicotineType,
    QuitAttempt,
    QuitAttemptStatus,
    SmokingProfile,
    SosSession,
    User,
    UserResponse,
    UserResponseType,
)
from app.db.session import configure_sqlite_foreign_keys
from app.services.idempotency import IdempotencyConflictError, execute_idempotent
from app.services.user_responses import user_response_memory


async def make_sessions(tmp_path, name: str = "p1.db"):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    configure_sqlite_foreign_keys(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def seed_profile(sessions, telegram_id: int = 10001) -> int:
    async with sessions() as session:
        user = User(telegram_id=telegram_id, telegram_first_name="Security")
        session.add(user)
        await session.flush()
        session.add(
            SmokingProfile(
                user_id=user.id,
                nicotine_type=NicotineType.CIGARETTES,
                years_of_use=Decimal("3"),
                daily_units=Decimal("10"),
                units_per_package=Decimal("20"),
                package_price=Decimal("250"),
                monthly_expense=Decimal("3750"),
                yearly_expense=Decimal("45000"),
                lifetime_expense=Decimal("135000"),
                projected_five_year_expense=Decimal("225000"),
            )
        )
        session.add(
            QuitAttempt(
                user_id=user.id,
                started_at=datetime.now(timezone.utc),
                status=QuitAttemptStatus.ACTIVE,
                active_marker=True,
            )
        )
        await session.commit()
        return user.id


async def load_context(sessions, user_id: int):
    session = sessions()
    user = await session.get(User, user_id)
    profile = await session.scalar(
        select(SmokingProfile).where(SmokingProfile.user_id == user_id)
    )
    assert user is not None and profile is not None
    return session, (user, profile, session)


@pytest.mark.asyncio
async def test_concurrent_lapse_retry_creates_one_lapse_and_one_side_effect(tmp_path):
    sessions, engine = await make_sessions(tmp_path, "lapse.db")
    user_id = await seed_profile(sessions)
    session_a, context_a = await load_context(sessions, user_id)
    session_b, context_b = await load_context(sessions, user_id)
    request = LapseRequest(lapse_type=LapseType.SINGLE.value, trigger_id="stress")

    first, second = await asyncio.gather(
        register_lapse(request, "lapse-retry-key", context_a),
        register_lapse(request, "lapse-retry-key", context_b),
    )
    assert first["id"] == second["id"]
    async with sessions() as session:
        assert await session.scalar(select(func.count(NicotineLapse.id))) == 1
        attempt = await session.scalar(select(QuitAttempt))
        assert attempt is not None and attempt.status == QuitAttemptStatus.RELAPSED
    await session_a.close()
    await session_b.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_desire_and_sos_retry_create_one_record_each(tmp_path):
    sessions, engine = await make_sessions(tmp_path, "events.db")
    user_id = await seed_profile(sessions)
    desire_a, context_a = await load_context(sessions, user_id)
    desire_b, context_b = await load_context(sessions, user_id)
    desire = DesireLogRequest(intensity=7, trigger_id="stress", emotion="tired")
    results = await asyncio.gather(
        create_desire_log(desire, "desire-retry-key", context_a),
        create_desire_log(desire, "desire-retry-key", context_b),
    )
    assert results[0]["id"] == results[1]["id"]

    sos_a, sos_context_a = await load_context(sessions, user_id)
    sos_b, sos_context_b = await load_context(sessions, user_id)
    sos = SosStartRequest(intensity_before=8, trigger_id="stress")
    sessions_result = await asyncio.gather(
        start_sos(sos, "sos-start-key", sos_context_a),
        start_sos(sos, "sos-start-key", sos_context_b),
    )
    assert sessions_result[0]["id"] == sessions_result[1]["id"]
    async with sessions() as session:
        assert await session.scalar(select(func.count(NicotineDesireLog.id))) == 1
        assert await session.scalar(select(func.count(SosSession.id))) == 1
    for session in (desire_a, desire_b, sos_a, sos_b):
        await session.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_idempotency_conflict_user_and_operation_isolation(tmp_path):
    sessions, engine = await make_sessions(tmp_path, "isolation.db")
    user_a = await seed_profile(sessions, 10101)
    user_b = await seed_profile(sessions, 20202)

    async def run(user_id: int, operation_type: str, value: int):
        async with sessions() as session:
            return await execute_idempotent(
                session,
                user_id=user_id,
                operation_type=operation_type,
                idempotency_key="shared-isolated-key",
                payload={"value": value},
                operation=lambda: asyncio.sleep(0, result={"value": value}),
            )

    assert await run(user_a, "one", 1) == {"value": 1}
    assert await run(user_a, "one", 1) == {"value": 1}
    assert await run(user_b, "one", 2) == {"value": 2}
    assert await run(user_a, "two", 3) == {"value": 3}
    with pytest.raises(IdempotencyConflictError, match="другими данными"):
        await run(user_a, "one", 9)
    async with sessions() as session:
        assert await session.scalar(select(func.count(IdempotencyRecord.id))) == 3
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_response_concurrent_insert_has_one_logical_row(tmp_path):
    sessions, engine = await make_sessions(tmp_path, "responses.db")
    user_id = await seed_profile(sessions)

    async def remember():
        async with sessions() as session:
            response = await user_response_memory.remember(
                session,
                user_id=user_id,
                response_type=UserResponseType.COPING_ACTION,
                value="Выпить воды",
                source="test",
                context_id="stress",
            )
            await session.commit()
            return response.id

    first, second = await asyncio.gather(remember(), remember())
    assert first == second
    async with sessions() as session:
        assert await session.scalar(select(func.count(UserResponse.id))) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_foreign_keys_are_enabled_per_connection(tmp_path):
    sessions, engine = await make_sessions(tmp_path, "foreign-keys.db")
    async with engine.connect() as connection:
        assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_user_response_duplicates_are_reconciled_without_losing_counters(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    import app.db.session as db_session

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    async with engine.begin() as connection:
        await connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, telegram_id BIGINT NOT NULL, "
            "telegram_first_name VARCHAR(255) NOT NULL)"
        ))
        await connection.execute(text(
            "CREATE TABLE user_responses (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
            "response_type VARCHAR(30) NOT NULL, value VARCHAR(1000) NOT NULL, "
            "normalized_value VARCHAR(1000) NOT NULL, context_id VARCHAR(100), "
            "parent_response_id INTEGER, focus VARCHAR(30), source VARCHAR(50) NOT NULL, "
            "source_ref VARCHAR(150), usage_count INTEGER NOT NULL, "
            "effectiveness_sum INTEGER NOT NULL, effectiveness_samples INTEGER NOT NULL, "
            "created_at DATETIME, last_used_at DATETIME, updated_at DATETIME)"
        ))
        await connection.execute(text(
            "INSERT INTO users VALUES (1, 12345, 'Existing')"
        ))
        await connection.execute(text(
            "INSERT INTO user_responses VALUES "
            "(1,1,'COPING_ACTION','Вода','вода','stress',NULL,NULL,'program',NULL,2,3,1,"
            "'2026-01-01','2026-01-01','2026-01-01'),"
            "(2,1,'COPING_ACTION','Вода.','вода','stress',NULL,NULL,'sos',NULL,4,5,2,"
            "'2026-01-02','2026-01-02','2026-01-02')"
        ))
    monkeypatch.setattr(db_session, "engine", engine)
    await db_session.init_db()
    async with engine.connect() as connection:
        rows = (await connection.execute(text(
            "SELECT usage_count, effectiveness_sum, effectiveness_samples, dedup_key "
            "FROM user_responses"
        ))).all()
        indexes = await connection.run_sync(
            lambda sync: {item["name"] for item in __import__("sqlalchemy").inspect(sync).get_indexes("user_responses")}
        )
    assert len(rows) == 1
    assert rows[0][:3] == (6, 8, 3)
    assert rows[0].dedup_key
    assert "uq_user_response_user_dedup_key" in indexes
    await engine.dispose()


@pytest.mark.asyncio
async def test_docs_hosts_and_security_headers_follow_environment():
    assert documentation_config(False)["docs_url"] == "/docs"
    assert documentation_config(True) == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }
    app = FastAPI(**documentation_config(True))

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.add_middleware(SecurityHeadersMiddleware, production=True)
    app.add_middleware(
        ProductionTrustedHostMiddleware, allowed_hosts=("airtgbot.ru",)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://airtgbot.ru"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.headers["strict-transport-security"].startswith("max-age=")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert (await client.get("/docs")).status_code == 404
        rejected = await client.get(
            "/health", headers={"Host": "attacker.invalid"}
        )
        assert rejected.status_code == 400


def test_frontend_controlled_strings_and_metadata_are_bounded():
    with pytest.raises(ValidationError):
        DesireLogRequest(intensity=5, trigger_id="x" * 101)
    with pytest.raises(ValidationError):
        SosActionCompleteRequest(metadata={"nested": {"value": "x" * 9000}})

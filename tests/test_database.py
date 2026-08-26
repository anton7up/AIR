import asyncio
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import User
from app.db.repositories import UserRepository
from app.services.expenses import ExpenseCalculator


@pytest.mark.asyncio
async def test_onboarding_can_update_existing_user(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    answers = {
        "gender": "male",
        "had_quit_attempts": True,
        "nicotine_type": "cigarettes",
        "cig_daily": 10,
        "cig_years": 5,
        "cig_pack_size": 20,
        "cig_pack_price": 200,
        "acquisition_source": "telegram",
    }
    result = ExpenseCalculator().calculate(answers)
    async with sessions() as session:
        repository = UserRepository(session)
        await repository.save_onboarding(42, "Alex", "alex", answers, result)
        answers["acquisition_source"] = "friends"
        await repository.save_onboarding(42, "Alex", "alex", answers, result)

    async with sessions() as session:
        users = (await session.scalars(select(User))).all()
        assert len(users) == 1
        assert users[0].acquisition_source == "friends"

    await engine.dispose()


@pytest.mark.asyncio
async def test_schema_initialization_is_safe_when_started_concurrently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.db.session as db_session

    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'concurrent.db'}"
    )
    monkeypatch.setattr(db_session, "engine", test_engine)

    await asyncio.gather(db_session.init_db(), db_session.init_db())

    async with test_engine.connect() as connection:
        tables = await connection.run_sync(
            lambda sync_connection: set(
                __import__("sqlalchemy").inspect(sync_connection).get_table_names()
            )
        )
    assert {
        "users",
        "smoking_profiles",
        "subscriptions",
        "quit_attempts",
        "program_day_states",
        "dev_program_day_states",
        "program_profiles",
        "nicotine_desire_logs",
        "nicotine_lapses",
        "sos_actions",
        "user_responses",
    } <= tables
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_schema_adds_sos2_columns_to_legacy_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.db.session as db_session

    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'legacy-sos.db'}"
    )
    async with test_engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE TABLE sos_sessions ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "exercise_type VARCHAR(50) NOT NULL, completed_at DATETIME NOT NULL)"
            )
        )
        await connection.execute(
            text(
                "CREATE TABLE sos_actions ("
                "id INTEGER PRIMARY KEY, sos_session_id INTEGER NOT NULL, "
                "support_type VARCHAR(100) NOT NULL, support_action VARCHAR(100), "
                "started_at DATETIME NOT NULL, completed_at DATETIME, "
                "sequence_number INTEGER NOT NULL)"
            )
        )
    monkeypatch.setattr(db_session, "engine", test_engine)

    await db_session.init_db()

    async with test_engine.connect() as connection:
        columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"]
                for column in inspect(sync_connection).get_columns("sos_actions")
            }
        )
        session_columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"]
                for column in inspect(sync_connection).get_columns("sos_sessions")
            }
        )
    assert {"trigger_id", "intensity_before", "intensity_after", "metadata_json", "user_response_id"} <= columns
    assert {"trigger_id", "intensity_before", "intensity_after", "reason_response_id"} <= session_columns
    await test_engine.dispose()

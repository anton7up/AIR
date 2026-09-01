import asyncio
from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db import models as _models  # noqa: F401 -- registers all tables in metadata
from app.db.base import Base

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
session_factory = async_sessionmaker(engine, expire_on_commit=False)
_init_db_lock = asyncio.Lock()


async def init_db() -> None:
    # The bot and FastAPI start concurrently in the combined process. SQLite's
    # check-first DDL is not atomic, so schema initialization must be serialized.
    async with _init_db_lock:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            if connection.dialect.name == "sqlite":
                columns = await connection.run_sync(
                    lambda sync_connection: {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("users")
                    }
                )
                if "quit_started_at" not in columns:
                    await connection.execute(
                        text("ALTER TABLE users ADD COLUMN quit_started_at DATETIME")
                    )
                if "motivation" not in columns:
                    await connection.execute(
                        text("ALTER TABLE users ADD COLUMN motivation VARCHAR(1000)")
                    )
                if "program_started_at" not in columns:
                    await connection.execute(
                        text("ALTER TABLE users ADD COLUMN program_started_at DATETIME")
                    )
                if "receipt_email" not in columns:
                    await connection.execute(
                        text("ALTER TABLE users ADD COLUMN receipt_email VARCHAR(320)")
                    )
                if "personal_data_consent_at" not in columns:
                    await connection.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN "
                            "personal_data_consent_at DATETIME"
                        )
                    )
                if "personal_data_consent_version" not in columns:
                    await connection.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN "
                            "personal_data_consent_version VARCHAR(20)"
                        )
                    )

                payment_columns = await connection.run_sync(
                    lambda sync_connection: {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("payment_orders")
                    }
                )
                if "receipt_status" not in payment_columns:
                    await connection.execute(
                        text(
                            "ALTER TABLE payment_orders ADD COLUMN receipt_status "
                            "VARCHAR(20) NOT NULL DEFAULT 'pending'"
                        )
                    )
                if "receipt_sent_at" not in payment_columns:
                    await connection.execute(
                        text("ALTER TABLE payment_orders ADD COLUMN receipt_sent_at DATETIME")
                    )
                await connection.execute(
                    text(
                        "UPDATE users SET program_started_at = quit_started_at "
                        "WHERE program_started_at IS NULL AND quit_started_at IS NOT NULL"
                    )
                )

                sos_columns = await connection.run_sync(
                    lambda sync_connection: {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("sos_sessions")
                    }
                )
                sos_migrations = {
                    "quit_attempt_id": "INTEGER",
                    "started_at": "DATETIME",
                    "finished_at": "DATETIME",
                    "trigger_id": "VARCHAR(100)",
                    "intensity_before": "INTEGER",
                    "support_type": "VARCHAR(100)",
                    "support_action": "VARCHAR(100)",
                    "intensity_after": "INTEGER",
                    "nicotine_used_after": "BOOLEAN",
                    "reason_response_id": "INTEGER",
                }
                for column_name, column_type in sos_migrations.items():
                    if column_name not in sos_columns:
                        await connection.execute(
                            text(
                                f"ALTER TABLE sos_sessions ADD COLUMN "
                                f"{column_name} {column_type}"
                            )
                        )
                await connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_sos_sessions_reason_response_id "
                        "ON sos_sessions (reason_response_id)"
                    )
                )

                action_columns = await connection.run_sync(
                    lambda sync_connection: {
                        column["name"]
                        for column in inspect(sync_connection).get_columns("sos_actions")
                    }
                )
                action_migrations = {
                    "trigger_id": "VARCHAR(100)",
                    "intensity_before": "INTEGER",
                    "intensity_after": "INTEGER",
                    "metadata_json": "JSON",
                    "user_response_id": "INTEGER",
                }
                for column_name, column_type in action_migrations.items():
                    if column_name not in action_columns:
                        await connection.execute(
                            text(
                                f"ALTER TABLE sos_actions ADD COLUMN "
                                f"{column_name} {column_type}"
                            )
                        )
                await connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_sos_actions_user_response_id "
                        "ON sos_actions (user_response_id)"
                    )
                )


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session

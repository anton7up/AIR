import asyncio
import logging
import sqlite3
from collections.abc import AsyncIterator

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db import models as _models  # noqa: F401 -- registers all tables in metadata
from app.db.base import Base
from app.db.models import UserResponseType
from app.services.user_responses import logical_response_key

logger = logging.getLogger(__name__)

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)


def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
    """SQLite disables FK enforcement per connection unless explicitly enabled."""
    try:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except (AttributeError, sqlite3.DatabaseError):
        # Non-SQLite database drivers do not support this PRAGMA.
        return


def configure_sqlite_foreign_keys(async_engine: AsyncEngine) -> None:
    if async_engine.url.get_backend_name() != "sqlite":
        return
    event.listen(
        async_engine.sync_engine,
        "connect",
        _enable_sqlite_foreign_keys,
    )


configure_sqlite_foreign_keys(engine)
session_factory = async_sessionmaker(engine, expire_on_commit=False)
_init_db_lock = asyncio.Lock()


def _response_type_from_db(value: str) -> UserResponseType:
    try:
        return UserResponseType(value)
    except ValueError:
        return UserResponseType[value]


async def _migrate_user_response_dedup(connection: AsyncConnection) -> None:
    columns = await connection.run_sync(
        lambda sync_connection: {
            column["name"]
            for column in inspect(sync_connection).get_columns("user_responses")
        }
    )
    if "dedup_key" not in columns:
        await connection.execute(
            text("ALTER TABLE user_responses ADD COLUMN dedup_key VARCHAR(64)")
        )

    # Reconcile legacy duplicates using exactly the previous SELECT identity.
    # Usage/effectiveness counters and every known reference are folded into the
    # oldest row. Re-run because re-parenting may reveal a second-level duplicate.
    for _ in range(20):
        result = await connection.execute(
            text(
                "SELECT id, user_id, response_type, value, normalized_value, "
                "context_id, parent_response_id, focus, usage_count, "
                "effectiveness_sum, effectiveness_samples, created_at, "
                "last_used_at, updated_at FROM user_responses ORDER BY id"
            )
        )
        rows = list(result.mappings())
        groups: dict[tuple[int, str], list[RowMapping]] = {}
        for row in rows:
            key = logical_response_key(
                _response_type_from_db(str(row["response_type"])),
                str(row["normalized_value"]),
                row["context_id"],
                row["parent_response_id"],
                row["focus"],
            )
            groups.setdefault((int(row["user_id"]), key), []).append(row)
        duplicates = [items for items in groups.values() if len(items) > 1]
        if not duplicates:
            for (user_id, key), items in groups.items():
                await connection.execute(
                    text(
                        "UPDATE user_responses SET dedup_key=:key "
                        "WHERE id=:id AND user_id=:user_id"
                    ),
                    {"key": key, "id": items[0]["id"], "user_id": user_id},
                )
            break
        for items in duplicates:
            survivor = items[0]
            duplicate_ids = [int(item["id"]) for item in items[1:]]
            latest = max(
                items,
                key=lambda item: (
                    str(item["last_used_at"] or ""),
                    str(item["updated_at"] or ""),
                    int(item["id"]),
                ),
            )
            params = {
                "survivor": int(survivor["id"]),
                "usage": sum(int(item["usage_count"] or 1) for item in items),
                "effect_sum": sum(int(item["effectiveness_sum"] or 0) for item in items),
                "effect_samples": sum(
                    int(item["effectiveness_samples"] or 0) for item in items
                ),
                "value": latest["value"],
                "created": min(str(item["created_at"] or "") for item in items),
                "last_used": latest["last_used_at"],
                "updated": latest["updated_at"],
            }
            placeholders = ",".join(str(item_id) for item_id in duplicate_ids)
            await connection.execute(
                text(
                    "UPDATE user_responses SET value=:value, usage_count=:usage, "
                    "effectiveness_sum=:effect_sum, effectiveness_samples=:effect_samples, "
                    "created_at=:created, last_used_at=:last_used, updated_at=:updated "
                    "WHERE id=:survivor"
                ),
                params,
            )
            for table_name, column_name in (
                ("user_responses", "parent_response_id"),
                ("sos_sessions", "reason_response_id"),
                ("sos_actions", "user_response_id"),
            ):
                await connection.execute(
                    text(
                        f"UPDATE {table_name} SET {column_name}=:survivor "
                        f"WHERE {column_name} IN ({placeholders})"
                    ),
                    {"survivor": int(survivor["id"])},
                )
            await connection.execute(
                text(f"DELETE FROM user_responses WHERE id IN ({placeholders})")
            )
    else:
        raise RuntimeError("UserResponse duplicate reconciliation did not converge")

    await connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_response_user_dedup_key "
            "ON user_responses (user_id, dedup_key)"
        )
    )


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

                support_message_columns = await connection.run_sync(
                    lambda sync_connection: {
                        column["name"]
                        for column in inspect(sync_connection).get_columns(
                            "support_messages"
                        )
                    }
                )
                if "telegram_chat_id" not in support_message_columns:
                    await connection.execute(
                        text(
                            "ALTER TABLE support_messages ADD COLUMN "
                            "telegram_chat_id BIGINT"
                        )
                    )
                if "telegram_message_id" not in support_message_columns:
                    await connection.execute(
                        text(
                            "ALTER TABLE support_messages ADD COLUMN "
                            "telegram_message_id BIGINT"
                        )
                    )
                await connection.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS "
                        "uq_support_message_telegram_source ON support_messages "
                        "(telegram_chat_id, telegram_message_id)"
                    )
                )

                await _migrate_user_response_dedup(connection)
                await connection.execute(
                    text(
                        "DELETE FROM idempotency_records "
                        "WHERE expires_at < CURRENT_TIMESTAMP"
                    )
                )
                orphan_rows = (
                    await connection.execute(text("PRAGMA foreign_key_check"))
                ).fetchmany(20)
                if orphan_rows:
                    logger.warning(
                        "SQLite legacy orphan rows detected; no data was changed: count_at_least=%s",
                        len(orphan_rows),
                    )


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session

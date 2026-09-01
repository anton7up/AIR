from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"


class NicotineType(StrEnum):
    CIGARETTES = "cigarettes"
    HEATED_TOBACCO = "heated_tobacco"
    VAPE = "vape"
    SNUS = "snus"
    HOOKAH = "hookah"


class SubscriptionStatus(StrEnum):
    FREE = "free"
    INACTIVE = "inactive"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PaymentOrderStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"


class ReceiptStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"


class QuitAttemptStatus(StrEnum):
    ACTIVE = "active"
    FINISHED = "finished"
    RELAPSED = "relapsed"


class LapseType(StrEnum):
    SINGLE = "single"
    MULTIPLE = "multiple"
    REGULAR = "regular"


class UserResponseType(StrEnum):
    TRIGGER = "trigger"
    REASON = "reason"
    COPING_ACTION = "coping_action"
    REPLACEMENT = "replacement"
    MOTIVATION = "motivation"
    PLAN_ACTION = "plan_action"
    REFLECTION = "reflection"
    SOCIAL_RESPONSE = "social_response"
    LAPSE_PLAN = "lapse_plan"
    GENERAL = "general"


def enum_column(enum_class: type[StrEnum], name: str):
    return Enum(enum_class, name=name, native_enum=False, validate_strings=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    telegram_first_name: Mapped[str] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gender: Mapped[Gender | None] = mapped_column(
        enum_column(Gender, "gender"), nullable=True
    )
    had_quit_attempts: Mapped[bool | None] = mapped_column(nullable=True)
    acquisition_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    quit_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    program_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    motivation: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    receipt_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    personal_data_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    personal_data_consent_version: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    smoking_profile: Mapped[SmokingProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    payment_orders: Mapped[list[PaymentOrder]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    program_completions: Mapped[list[ProgramDayCompletion]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sos_sessions: Mapped[list[SosSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    quit_attempts: Mapped[list[QuitAttempt]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    program_states: Mapped[list[ProgramDayState]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    dev_program_states: Mapped[list[DevProgramDayState]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    program_profile: Mapped[ProgramProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    desire_logs: Mapped[list[NicotineDesireLog]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    nicotine_lapses: Mapped[list[NicotineLapse]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    responses: Mapped[list[UserResponse]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SmokingProfile(Base):
    __tablename__ = "smoking_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    nicotine_type: Mapped[NicotineType] = mapped_column(
        enum_column(NicotineType, "nicotine_type")
    )
    years_of_use: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    daily_units: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    units_per_package: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    package_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    consumption_parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    monthly_expense: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    yearly_expense: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    lifetime_expense: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    projected_five_year_expense: Mapped[Decimal] = mapped_column(Numeric(16, 2))

    user: Mapped[User] = relationship(back_populates="smoking_profile")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan: Mapped[str] = mapped_column(String(100), default="free")
    status: Mapped[SubscriptionStatus] = mapped_column(
        enum_column(SubscriptionStatus, "subscription_status"),
        default=SubscriptionStatus.INACTIVE,
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="subscriptions")


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[str] = mapped_column(String(50), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[PaymentOrderStatus] = mapped_column(
        enum_column(PaymentOrderStatus, "payment_order_status"),
        default=PaymentOrderStatus.PENDING,
        index=True,
    )
    yookassa_payment_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(36), unique=True)
    confirmation_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    receipt_email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Keep this as a string: the additive SQLite migration stores enum values
    # ("pending"/"sent"), while SQLAlchemy Enum stores member names by default.
    # A string column remains compatible with already migrated production rows.
    receipt_status: Mapped[str] = mapped_column(
        String(20),
        default=ReceiptStatus.PENDING.value,
        server_default=ReceiptStatus.PENDING.value,
    )
    receipt_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="payment_orders")


class ProgramDayCompletion(Base):
    __tablename__ = "program_day_completions"
    __table_args__ = (UniqueConstraint("user_id", "day_number", name="uq_program_completion_user_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day_number: Mapped[int]
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="program_completions")


class ProgramDayState(Base):
    __tablename__ = "program_day_states"
    __table_args__ = (
        UniqueConstraint("user_id", "day_number", name="uq_program_state_user_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day_number: Mapped[int] = mapped_column(Integer)
    current_step: Mapped[str] = mapped_column(String(100), default="start")
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="program_states")


class DevProgramDayState(Base):
    __tablename__ = "dev_program_day_states"
    __table_args__ = (
        UniqueConstraint("user_id", "day_number", name="uq_dev_program_state_user_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day_number: Mapped[int] = mapped_column(Integer)
    current_step: Mapped[str] = mapped_column(String(100), default="start")
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="dev_program_states")


class ProgramProfile(Base):
    __tablename__ = "program_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    quit_reasons: Mapped[list] = mapped_column(JSON, default=list)
    primary_quit_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_triggers: Mapped[list] = mapped_column(JSON, default=list)
    primary_triggers: Mapped[list] = mapped_column(JSON, default=list)
    nicotine_beliefs: Mapped[list] = mapped_column(JSON, default=list)
    quit_concerns: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="program_profile")


class UserResponse(Base):
    __tablename__ = "user_responses"
    __table_args__ = (
        CheckConstraint("usage_count >= 1", name="ck_user_response_usage_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    response_type: Mapped[UserResponseType] = mapped_column(
        enum_column(UserResponseType, "user_response_type"), index=True
    )
    value: Mapped[str] = mapped_column(String(1000))
    normalized_value: Mapped[str] = mapped_column(String(1000), index=True)
    context_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    parent_response_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_responses.id"), nullable=True, index=True
    )
    focus: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source: Mapped[str] = mapped_column(String(50))
    source_ref: Mapped[str | None] = mapped_column(String(150), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=1)
    effectiveness_sum: Mapped[int] = mapped_column(Integer, default=0)
    effectiveness_samples: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="responses")
    parent: Mapped[UserResponse | None] = relationship(remote_side="UserResponse.id")


class QuitAttempt(Base):
    __tablename__ = "quit_attempts"
    __table_args__ = (
        UniqueConstraint("user_id", "active_marker", name="uq_quit_attempt_active_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[QuitAttemptStatus] = mapped_column(
        enum_column(QuitAttemptStatus, "quit_attempt_status"),
        default=QuitAttemptStatus.ACTIVE,
    )
    end_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active_marker: Mapped[bool | None] = mapped_column(Boolean, default=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="quit_attempts")
    desire_logs: Mapped[list[NicotineDesireLog]] = relationship(back_populates="quit_attempt")
    lapses: Mapped[list[NicotineLapse]] = relationship(back_populates="quit_attempt")
    sos_sessions: Mapped[list[SosSession]] = relationship(back_populates="quit_attempt")


class NicotineDesireLog(Base):
    __tablename__ = "nicotine_desire_logs"
    __table_args__ = (CheckConstraint("intensity BETWEEN 1 AND 10", name="ck_desire_intensity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    quit_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("quit_attempts.id"), nullable=True, index=True
    )
    intensity: Mapped[int] = mapped_column(Integer)
    trigger_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped[User] = relationship(back_populates="desire_logs")
    quit_attempt: Mapped[QuitAttempt | None] = relationship(back_populates="desire_logs")


class NicotineLapse(Base):
    __tablename__ = "nicotine_lapses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    quit_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("quit_attempts.id"), nullable=True, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lapse_type: Mapped[LapseType] = mapped_column(enum_column(LapseType, "lapse_type"))
    trigger_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="nicotine_lapses")
    quit_attempt: Mapped[QuitAttempt | None] = relationship(back_populates="lapses")


class SosSession(Base):
    __tablename__ = "sos_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exercise_type: Mapped[str] = mapped_column(String(50))
    quit_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("quit_attempts.id"), nullable=True, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason_response_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_responses.id"), nullable=True, index=True
    )
    intensity_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    support_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    support_action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    intensity_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nicotine_used_after: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="sos_sessions")
    quit_attempt: Mapped[QuitAttempt | None] = relationship(back_populates="sos_sessions")
    actions: Mapped[list[SosAction]] = relationship(
        back_populates="sos_session",
        cascade="all, delete-orphan",
        order_by="SosAction.sequence_number",
    )


class SosAction(Base):
    __tablename__ = "sos_actions"
    __table_args__ = (
        UniqueConstraint(
            "sos_session_id",
            "sequence_number",
            name="uq_sos_action_session_sequence",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sos_session_id: Mapped[int] = mapped_column(
        ForeignKey("sos_sessions.id"), index=True
    )
    support_type: Mapped[str] = mapped_column(String(100))
    support_action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_response_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_responses.id"), nullable=True, index=True
    )
    trigger_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    intensity_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intensity_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer)

    sos_session: Mapped[SosSession] = relationship(back_populates="actions")

    @property
    def effect_delta(self) -> int | None:
        if self.intensity_before is None or self.intensity_after is None:
            return None
        return self.intensity_before - self.intensity_after

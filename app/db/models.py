import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Integer, DateTime, Text, JSON, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.db import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="api")
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    tool_args: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tool_result_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    policy_decision: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    decision_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    intent_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    citations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    fallback_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    compliance_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    compliance_issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    message_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

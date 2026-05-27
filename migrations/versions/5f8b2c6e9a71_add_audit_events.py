"""add_audit_events

Revision ID: 5f8b2c6e9a71
Revises: 0d5c9c8a3b10
Create Date: 2026-05-23 13:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5f8b2c6e9a71"
down_revision: Union[str, Sequence[str], None] = "0d5c9c8a3b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("rule_version", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("tool_args", sa.JSON(), nullable=False),
        sa.Column("tool_result_preview", sa.Text(), nullable=False),
        sa.Column("policy_decision", sa.JSON(), nullable=False),
        sa.Column("compliance_passed", sa.Boolean(), nullable=True),
        sa.Column("compliance_issues", sa.JSON(), nullable=False),
        sa.Column("message_preview", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_trace_id", "audit_events", ["trace_id"])
    op.create_index("ix_audit_events_session_id", "audit_events", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_session_id", table_name="audit_events")
    op.drop_index("ix_audit_events_trace_id", table_name="audit_events")
    op.drop_table("audit_events")

"""add_decision_fields_to_audit

Revision ID: 0f2141d6f4a2
Revises: 5f8b2c6e9a71
Create Date: 2026-05-23 14:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0f2141d6f4a2"
down_revision: Union[str, Sequence[str], None] = "5f8b2c6e9a71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("decision_payload", sa.JSON(), nullable=True))
    op.add_column("audit_events", sa.Column("intent_type", sa.String(length=64), nullable=True))
    op.add_column("audit_events", sa.Column("action_type", sa.String(length=64), nullable=True))
    op.add_column("audit_events", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("audit_events", sa.Column("citations", sa.JSON(), nullable=True))
    op.add_column("audit_events", sa.Column("fallback_reason", sa.Text(), nullable=True))
    op.execute("UPDATE audit_events SET decision_payload = '{}'::json")
    op.execute("UPDATE audit_events SET intent_type = ''")
    op.execute("UPDATE audit_events SET action_type = ''")
    op.execute("UPDATE audit_events SET citations = '[]'::json")
    op.execute("UPDATE audit_events SET fallback_reason = ''")
    op.alter_column("audit_events", "decision_payload", nullable=False)
    op.alter_column("audit_events", "intent_type", nullable=False)
    op.alter_column("audit_events", "action_type", nullable=False)
    op.alter_column("audit_events", "citations", nullable=False)
    op.alter_column("audit_events", "fallback_reason", nullable=False)


def downgrade() -> None:
    op.drop_column("audit_events", "fallback_reason")
    op.drop_column("audit_events", "citations")
    op.drop_column("audit_events", "confidence")
    op.drop_column("audit_events", "action_type")
    op.drop_column("audit_events", "intent_type")
    op.drop_column("audit_events", "decision_payload")

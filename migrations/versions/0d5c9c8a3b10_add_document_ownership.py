"""add_document_ownership

Revision ID: 0d5c9c8a3b10
Revises: 588947b2348d
Create Date: 2026-05-23 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0d5c9c8a3b10"
down_revision: Union[str, Sequence[str], None] = "588947b2348d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("tenant_id", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("owner_user_id", sa.String(length=64), nullable=True))
    op.execute("UPDATE documents SET tenant_id = 'default', owner_user_id = 'unknown'")
    op.alter_column("documents", "tenant_id", nullable=False)
    op.alter_column("documents", "owner_user_id", nullable=False)
    op.create_index("ix_documents_tenant_owner", "documents", ["tenant_id", "owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_tenant_owner", table_name="documents")
    op.drop_column("documents", "owner_user_id")
    op.drop_column("documents", "tenant_id")

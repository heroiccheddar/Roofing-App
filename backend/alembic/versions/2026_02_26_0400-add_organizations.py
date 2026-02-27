"""Add organizations table and org membership to roofer_accounts.

Revision ID: add_organizations
Revises: a3f8c21d904e
Create Date: 2026-02-26 04:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "add_organizations"
down_revision: Union[str, None] = "a3f8c21d904e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("invite_code", sa.String(8), nullable=False, unique=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("roofer_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_organizations_invite_code", "organizations", ["invite_code"], unique=True)

    op.add_column(
        "roofer_accounts",
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True),
    )
    op.add_column(
        "roofer_accounts",
        sa.Column("org_role", sa.String(), nullable=True),
    )
    op.create_index("ix_roofer_accounts_organization_id", "roofer_accounts", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_roofer_accounts_organization_id", table_name="roofer_accounts")
    op.drop_column("roofer_accounts", "org_role")
    op.drop_column("roofer_accounts", "organization_id")
    op.drop_index("ix_organizations_invite_code", table_name="organizations")
    op.drop_table("organizations")

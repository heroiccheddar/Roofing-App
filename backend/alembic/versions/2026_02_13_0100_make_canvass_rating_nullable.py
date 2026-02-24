"""Make canvass_sessions.rating nullable.

Allows sessions to be created without a rating (set when session ends).

Revision ID: make_canvass_rating_nullable
Revises: add_display_name
Create Date: 2026-02-13
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "make_canvass_rating_nullable"
down_revision: Union[str, None] = "add_display_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "canvass_sessions",
        "rating",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "canvass_sessions",
        "rating",
        existing_type=sa.Integer(),
        nullable=False,
    )

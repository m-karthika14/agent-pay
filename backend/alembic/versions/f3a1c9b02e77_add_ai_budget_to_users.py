"""add ai budget to users

Revision ID: f3a1c9b02e77
Revises: d0bc94f8aa37
Create Date: 2026-08-27 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a1c9b02e77'
down_revision: Union[str, Sequence[str], None] = 'd0bc94f8aa37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('ai_budget_max_amount_minor', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('ai_budget_allow_addons', sa.Boolean(), nullable=True))
    op.add_column('users', sa.Column('ai_budget_expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'ai_budget_expires_at')
    op.drop_column('users', 'ai_budget_allow_addons')
    op.drop_column('users', 'ai_budget_max_amount_minor')

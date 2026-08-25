"""add mandate_id to carts

Revision ID: a53d11a41c37
Revises: 4ae917627462
Create Date: 2026-08-25 20:22:02.710566

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a53d11a41c37'
down_revision: Union[str, Sequence[str], None] = '4ae917627462'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('carts', sa.Column('mandate_id', sa.UUID(), nullable=True))
    # Named explicitly (autogenerate's `None` lets Postgres pick an implicit
    # name, which downgrade() then can't reliably reference -- verified live:
    # Postgres's own default naming for this exact column happens to be
    # 'carts_mandate_id_fkey', so naming it explicitly here changes nothing
    # about the already-applied schema, it just makes the name predictable).
    op.create_foreign_key('carts_mandate_id_fkey', 'carts', 'mandates', ['mandate_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('carts_mandate_id_fkey', 'carts', type_='foreignkey')
    op.drop_column('carts', 'mandate_id')

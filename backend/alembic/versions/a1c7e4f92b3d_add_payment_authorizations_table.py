"""add payment_authorizations table

Revision ID: a1c7e4f92b3d
Revises: f3a1c9b02e77
Create Date: 2026-08-29 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c7e4f92b3d'
down_revision: Union[str, Sequence[str], None] = 'f3a1c9b02e77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'payment_authorizations',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('razorpay_customer_id', sa.String(length=100), nullable=False),
        sa.Column('razorpay_token_id', sa.String(length=100), nullable=True),
        sa.Column('setup_razorpay_order_id', sa.String(length=100), nullable=True),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'ACTIVE', 'REVOKED', 'EXPIRED', 'FAILED', name='payment_authorization_status'),
            nullable=False,
        ),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('max_amount_minor', sa.Integer(), nullable=False),
        sa.Column('authorized_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('payment_authorizations')
    sa.Enum(name='payment_authorization_status').drop(op.get_bind(), checkfirst=False)

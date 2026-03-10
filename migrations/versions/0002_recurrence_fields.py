"""Add recurrence fields to events

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-10 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('events', sa.Column('recurrence_rule', sa.Text(), nullable=True))
    op.add_column('events', sa.Column('recurrence_json', postgresql.JSONB(), nullable=True))
    op.add_column('events', sa.Column('recurrence_master_id', postgresql.UUID(as_uuid=True),
                                       sa.ForeignKey('events.id', ondelete='SET NULL'), nullable=True))
    op.add_column('events', sa.Column('is_recurrence_master', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('events', sa.Column('recurrence_exception_date', sa.Date(), nullable=True))
    op.add_column('events', sa.Column('is_cancelled_occurrence', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('events', sa.Column('instance_index', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('events', 'instance_index')
    op.drop_column('events', 'is_cancelled_occurrence')
    op.drop_column('events', 'recurrence_exception_date')
    op.drop_column('events', 'is_recurrence_master')
    op.drop_column('events', 'recurrence_master_id')
    op.drop_column('events', 'recurrence_json')
    op.drop_column('events', 'recurrence_rule')

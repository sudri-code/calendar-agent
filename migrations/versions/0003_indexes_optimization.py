"""Optimization indexes

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-10 00:02:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_events_recurrence_master_id', 'events', ['recurrence_master_id'])
    op.create_index('ix_events_sync_group_id_role', 'events', ['sync_group_id', 'role'])
    op.create_index('ix_events_user_id_start_at', 'events', ['user_id', 'start_at'])


def downgrade() -> None:
    op.drop_index('ix_events_user_id_start_at', 'events')
    op.drop_index('ix_events_sync_group_id_role', 'events')
    op.drop_index('ix_events_recurrence_master_id', 'events')

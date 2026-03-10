"""Replace OAuth tokens with EWS credentials

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-10 00:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove OAuth / Azure-specific columns
    op.drop_column('exchange_accounts', 'tenant_id')
    op.drop_column('exchange_accounts', 'access_token_encrypted')
    op.drop_column('exchange_accounts', 'refresh_token_encrypted')
    op.drop_column('exchange_accounts', 'token_expires_at')

    # Add EWS credential columns
    op.add_column('exchange_accounts', sa.Column('ews_server', sa.Text(), nullable=False, server_default=''))
    op.add_column('exchange_accounts', sa.Column('domain', sa.Text(), nullable=True))
    op.add_column('exchange_accounts', sa.Column('username_encrypted', sa.Text(), nullable=False, server_default=''))
    op.add_column('exchange_accounts', sa.Column('password_encrypted', sa.Text(), nullable=False, server_default=''))
    op.add_column('exchange_accounts', sa.Column('auth_type', sa.Text(), nullable=False, server_default='NTLM'))

    # Remove server_defaults used only for migration (columns are NOT NULL in application)
    op.alter_column('exchange_accounts', 'ews_server', server_default=None)
    op.alter_column('exchange_accounts', 'username_encrypted', server_default=None)
    op.alter_column('exchange_accounts', 'password_encrypted', server_default=None)

    # Drop graph_subscriptions — not used with on-premises EWS
    op.drop_table('graph_subscriptions')


def downgrade() -> None:
    op.add_column('exchange_accounts', sa.Column('tenant_id', sa.Text(), nullable=True))
    op.add_column('exchange_accounts', sa.Column('access_token_encrypted', sa.Text(), nullable=False, server_default=''))
    op.add_column('exchange_accounts', sa.Column('refresh_token_encrypted', sa.Text(), nullable=False, server_default=''))
    op.add_column('exchange_accounts', sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')))

    op.drop_column('exchange_accounts', 'auth_type')
    op.drop_column('exchange_accounts', 'password_encrypted')
    op.drop_column('exchange_accounts', 'username_encrypted')
    op.drop_column('exchange_accounts', 'domain')
    op.drop_column('exchange_accounts', 'ews_server')

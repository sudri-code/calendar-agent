"""
Session factory for Celery tasks.
Uses NullPool to avoid event loop conflicts: each asyncio.run() call
in a Celery task gets fresh connections rather than reusing pooled ones
from a previous loop.
"""
import os

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool


def make_session_factory():
    database_url = os.environ.get("DATABASE_URL", "")
    engine = create_async_engine(database_url, poolclass=NullPool)
    return async_sessionmaker(engine, expire_on_commit=False)

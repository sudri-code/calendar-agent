import os
import pytest
import asyncio

# Set test environment variables
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://calendar_bot:changeme@localhost:5432/calendar_bot_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ=")  # base64 test key
os.environ.setdefault("MS_CLIENT_ID", "test-client-id")
os.environ.setdefault("MS_CLIENT_SECRET", "test-secret")
os.environ.setdefault("INTERNAL_API_KEY", "test-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

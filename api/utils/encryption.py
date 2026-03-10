from cryptography.fernet import Fernet
from api.config import settings


def _get_fernet() -> Fernet:
    key = settings.encryption_key
    if not key:
        raise ValueError("ENCRYPTION_KEY is not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    """Encrypt a string value using Fernet symmetric encryption."""
    f = _get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt a Fernet-encrypted string value."""
    f = _get_fernet()
    return f.decrypt(value.encode()).decode()

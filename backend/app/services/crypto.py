from cryptography.fernet import Fernet
from app.config import settings


def _f() -> Fernet:
    if not settings.ENCRYPTION_KEY:
        raise RuntimeError("ENCRYPTION_KEY مش موجود في .env")
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt(value: str) -> str:
    return _f().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _f().decrypt(value.encode()).decode()

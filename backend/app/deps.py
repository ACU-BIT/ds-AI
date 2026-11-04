
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Company, User


bearer = HTTPBearer(auto_error=False)

PBKDF2_ITERATIONS = 200_000
SALT_LENGTH = 16


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("كلمة المرور غير صالحة")

    salt = os.urandom(SALT_LENGTH)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )

    return f"{salt.hex()}:{hashed.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not isinstance(password, str) or not isinstance(stored, str):
        return False

    try:
        salt_hex, hash_hex = stored.split(":", 1)

        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)

        if len(salt) != SALT_LENGTH or len(expected_hash) != 32:
            return False

        calculated_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PBKDF2_ITERATIONS,
        )

        return hmac.compare_digest(calculated_hash, expected_hash)

    except (ValueError, TypeError):
        return False


def make_token(user_id: int) -> str:
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("معرّف المستخدم غير صالح")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=7)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm="HS256",
    )


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="لازم تسجّل دخول",
        )

    try:
        payload = jwt.decode(
            creds.credentials,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )

        subject = payload.get("sub")

        if not isinstance(subject, str) or not subject.isdigit():
            raise ValueError("Invalid token subject")

        user_id = int(subject)

    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="الجلسة انتهت أو غير صالحة",
        )

    user = db.get(User, user_id)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="مستخدم غير موجود",
        )

    return user


def current_company(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Company:
    company = db.get(Company, user.company_id)

    if not company:
        raise HTTPException(
            status_code=403,
            detail="الشركة المرتبطة بالحساب غير موجودة",
        )

    return company

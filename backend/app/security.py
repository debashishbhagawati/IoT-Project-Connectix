from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import os

from fastapi import HTTPException, status
from jose import JWTError, jwt

from .config import settings

PBKDF2_ITERATIONS = 200_000
PBKDF2_ALGORITHM = "sha256"
HASH_PREFIX = "pbkdf2_sha256"


def _pbkdf2(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(PBKDF2_ALGORITHM, password.encode("utf-8"), salt, iterations)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = _pbkdf2(password=password, salt=salt, iterations=PBKDF2_ITERATIONS)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("utf-8")
    hash_b64 = base64.urlsafe_b64encode(digest).decode("utf-8")
    return f"{HASH_PREFIX}${PBKDF2_ITERATIONS}${salt_b64}${hash_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        prefix, iterations_str, salt_b64, hash_b64 = password_hash.split("$", 3)
        if prefix != HASH_PREFIX:
            return False

        iterations = int(iterations_str)
        salt = base64.urlsafe_b64decode(salt_b64.encode("utf-8"))
        expected = base64.urlsafe_b64decode(hash_b64.encode("utf-8"))
    except Exception:
        return False

    computed = _pbkdf2(password=password, salt=salt, iterations=iterations)
    return hmac.compare_digest(computed, expected)


def create_access_token(role: str, user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)
    payload = {"role": role, "user_id": user_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc

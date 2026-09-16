from datetime import datetime, timedelta
import os
import bcrypt
import jwt

# JWT signing configuration. A development fallback keeps the local prototype
# runnable, while deployments can provide a strong secret through the
# DIAGNOSTIC_JWT_SECRET environment variable.
SECRET_KEY = os.getenv(
    "DIAGNOSTIC_JWT_SECRET",
    "dev-only-change-this-diagnostic-jwt-secret",
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24


def hash_password(password: str) -> str:
    """Takes a plain-text password and returns a secure bcrypt hash."""
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the stored database hash."""
    pwd_bytes = plain_password.encode("utf-8")[:72]
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hash_bytes)


def create_access_token(data: dict) -> str:
    """Creates a signed JWT containing payload data and expiration timestamp."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

"""
Minimal JWT auth — mirrors db_light/auth/jwt_utils.py but self-contained.
"""
import datetime as dt
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRE_MINUTES

_bearer = HTTPBearer(auto_error=False)


def create_access_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": dt.datetime.utcnow() + dt.timedelta(minutes=JWT_EXPIRE_MINUTES),
        "iat": dt.datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return user_id

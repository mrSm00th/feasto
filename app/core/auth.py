from datetime import UTC, datetime, timedelta
from typing import Annotated
import uuid
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.models as models
from app.core.config import settings
from app.db.database import get_db

password_hash = PasswordHash.recommended()

oauth_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/token")

oauth_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/users/token", auto_error=False
)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:

    return password_hash.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:

    # NOTE: Copying data as py dicts are mutable and are passed by reference,
    #  we don't want to modify the original data dict
    to_encode = data.copy()

    if expires_delta:

        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({"exp": expire})
    # NOTE: sub will be added in the caller func and contains the user_id

    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key.get_secret_value(), algorithm=settings.algorithm
    )

    return encoded_jwt


def verify_access_token(token: str) -> str | None:

    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=settings.algorithm,
            options={"require": ["exp", "sub"]},
        )

    except jwt.InvalidTokenError:
        return None

    else:
        return {
            "user_id": payload.get("sub"),
            "role": payload.get("role"),
        }


async def get_current_user(
    token: Annotated[str, Depends(oauth_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> models.User:

    user_id = verify_access_token(token)

    if user_id is None:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or Expired Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:

        user_id_uuid = uuid.UUID(user_id)

    except (TypeError, ValueError):

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or Expired Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(models.User).where(models.User.id == user_id_uuid))

    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or Expired Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


CurrentUser = Annotated[models.User, Depends(get_current_user)]

from fastapi import APIRouter, status, HTTPException, Depends
from app.schemas.user_schemas import CreateUser, UserPrivate, Token
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import app.db.models as models
from app.db.database import get_db
from typing import Annotated
from app.core.auth import CurrentUser, hash_password, verify_password, create_access_token

from fastapi.security import OAuth2PasswordRequestForm
from app.core.config import settings
from datetime import datetime, UTC, timedelta
router = APIRouter(prefix="/api/users", tags=["users"])

@router.post(
    "",
    response_model= UserPrivate,
    status_code = status.HTTP_201_CREATED,
)
async def create_user(
    user: CreateUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.full_name)==user.full_name.lower()
        )
    )

    existing_user= result.scalars().first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this full name already exists"
        )
    
    result = await db.execute(
        select(models.User).where(
            models.User.email == user.email
        )
    )

    existing_email = result.scalars().first()

    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    result = await db.execute(
        select(models.User).where(
            models.User.phone_number == user.phone_number)
    )
    
    existing_phone_number = result.scalars().first()

    if existing_phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this phone number already exists"
        )

    new_user = models.User(
        full_name = user.full_name,
        email = user.email,
        phone_number = user.phone_number,
        password_hash = hash_password(user.password),
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@router.post("/token", response_model = Token)
async def login_for_access_token(

    # NOTE: OAuth2 standard requires login credentials to be sent as form data, not JSON
    #username=alex&password=secret
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    
    # Note: OAuth2PasswordRequestForm uses "username" field, but we treat it as email
    result = await db.execute(
        select(models.User).where(models.User.email == form_data.username)
    )

    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.password_hash):
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes= settings.access_token_expire_minutes)
    access_token = create_access_token(
        data= {"sub": str(user.id)},
        expire_delta= access_token_expires,
    )

    return Token(
        access_token = access_token,
        token_type = "bearer"
    )

@router.get("/me", response_model=UserPrivate)
async def get_current_user(current_user: CurrentUser):
    return current_user
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.owner_applications.models as models
from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.users.models import UserRole
from app.schemas.owner_application_schemas import (
    OwnerApplicationCreate,
    OwnerApplicationResponse,
)

router = APIRouter(prefix="/partner", tags=["owner applications"])


@router.post(
    "/application",
    response_model=OwnerApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_application(
    data: OwnerApplicationCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user=Depends(require_roles(UserRole.CUSTOMER)),
):

    new_application = models.OwnerApplication(
        user_id=current_user.id,
        restaurant_name=data.restaurant_name,
        fssai_license_number=data.fssai_license_number,
        gst_number=data.gst_number,
        pan_number=data.pan_number,
        bank_account_number=data.bank_account_number,
    )

    try:
        db.add(new_application)
        await db.commit()
        await db.refresh(new_application)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="FSSAI number already exists")

    return new_application

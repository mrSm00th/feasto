from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.owner_applications.models import OwnerApplication
from app.modules.owner_applications.schemas import (
    OwnerApplicationCreate,
    OwnerApplicationResponse,
)
from app.modules.users.models import UserRole

router = APIRouter(prefix="/api/partner", tags=["owner applications"])


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
    result = await db.execute(
        select(OwnerApplication).where(
            OwnerApplication.applicant_id == current_user.id,
            OwnerApplication.status == "PENDING",
        )
    )

    existing_application = result.scalars().first()

    if existing_application:
        raise HTTPException(
            status_code=400, detail="You already have a pending application"
        )

    new_application = OwnerApplication(
        applicant_id=current_user.id,
        restaurant_name=data.restaurant_name,
        fssai_license_number=data.fssai_license_number,
        gst_number=data.gst_number,
    )

    try:
        db.add(new_application)
        await db.commit()
        await db.refresh(new_application)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="FSSAI number already exists")

    return new_application

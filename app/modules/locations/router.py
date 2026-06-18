from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.locations.models import City, CityStatus
from app.modules.locations.schemas import (
    LocationActivateRequest,
    LocationActivateResponse,
    LocationInactivationRequest,
    LocationInactivationResponse,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/locations", tags=["locations"])


@router.post("/activate", response_model=LocationActivateResponse)
async def activate_city(
    data: LocationActivateRequest,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    city_name = data.city_name.strip().lower()
    state = data.state.strip().lower()

    result = await db.execute(
        select(City).where(
            City.name == city_name,
            City.state == state,
        )
    )

    existing_city = result.scalars().first()

    if not existing_city:

        existing_city = City(
            name=city_name,
            state=state,
            status=CityStatus.ACTIVE,
            created_by=current_user.id,
        )

        db.add(existing_city)
        await db.commit()
        await db.refresh(existing_city)

        return existing_city

    if existing_city.status == CityStatus.ACTIVE:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="City already activated",
        )

    existing_city.status = CityStatus.ACTIVE

    await db.commit()
    await db.refresh(existing_city)

    return existing_city


@router.post("/inactivate", response_model=LocationInactivationResponse)
async def inactivate_city(
    data: LocationInactivationRequest,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    city_name = data.city_name.strip().lower()
    state = data.state.strip().lower()

    result = await db.execute(
        select(City).where(
            City.name == city_name,
            City.state == state,
        )
    )

    existing_city = result.scalars().first()

    if not existing_city:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City does not exist",
        )

    if existing_city.status == CityStatus.INACTIVE:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="City already inactivated",
        )

    existing_city.status = CityStatus.INACTIVE
    existing_city.inactivated_by = current_user.id
    existing_city.inactivation_reason = data.inactivation_reason
    existing_city.inactivated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(existing_city)

    return existing_city

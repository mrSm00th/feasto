import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.addresses.models import Address
from app.modules.addresses.schemas import (
    AddressCreateSchema,
    AddressListResponseSchema,
    AddressPatchSchema,
    AddressResponseSchema,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/users/me/addresses", tags=["addresses"])


@router.post(
    "",
    response_model=AddressResponseSchema,
    status_code=status.HTTP_201_CREATED,
    description=("add a new address to your account"),
)
async def add_address(
    data: AddressCreateSchema,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # If this address is set as default, unset all existing defaults first
    if data.is_default:
        await db.execute(
            update(Address)
            .where(Address.user_id == current_user.id)
            .values(is_default=False)
        )

    address = Address(
        user_id=current_user.id,
        label=data.label,
        address_line_1=data.address_line_1,
        address_line_2=data.address_line_2,
        city=data.city,
        state=data.state,
        postal_code=data.postal_code,
        country=data.country,
        latitude=data.latitude,
        longitude=data.longitude,
        is_default=data.is_default,
    )

    db.add(address)
    await db.commit()
    await db.refresh(address)
    return address


@router.get(
    "",
    response_model=AddressListResponseSchema,
    description=("list all your saved addresses"),
)
async def get_all_addresses(
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Address)
        .where(Address.user_id == current_user.id)
        .order_by(Address.is_default.desc(), Address.created_at.desc())
    )
    addresses = result.scalars().all()

    return AddressListResponseSchema(
        total=len(addresses),
        addresses=addresses,
    )


@router.get(
    "/{address_id}",
    response_model=AddressResponseSchema,
    description=("get one specific address"),
)
async def get_address(
    address_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Address).where(
            Address.id == address_id,
            Address.user_id == current_user.id,
        )
    )
    address = result.scalar_one_or_none()

    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    return address


@router.patch(
    "/{address_id}",
    response_model=AddressResponseSchema,
    description=("update parts of an address"),
)
async def update_address(
    address_id: uuid.UUID,
    data: AddressPatchSchema,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Address).where(
            Address.id == address_id,
            Address.user_id == current_user.id,
        )
    )
    address = result.scalar_one_or_none()

    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    has_changes = False

    # If setting this as default, unset others first
    if data.is_default is True and not address.is_default:
        await db.execute(
            update(Address)
            .where(Address.user_id == current_user.id)
            .values(is_default=False)
        )
        address.is_default = True
        has_changes = True

    fields = [
        "label",
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "postal_code",
        "country",
        "latitude",
        "longitude",
    ]

    for field in fields:
        value = getattr(data, field)
        if value is not None:
            setattr(address, field, value)
            has_changes = True

    if not has_changes:
        return address

    await db.commit()
    await db.refresh(address)
    return address


@router.delete(
    "/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    description=("remove an address"),
)
async def delete_address(
    address_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Address).where(
            Address.id == address_id,
            Address.user_id == current_user.id,
        )
    )
    address = result.scalar_one_or_none()

    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    await db.delete(address)
    await db.commit()

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.orders.models import Order, OrderStatus
from app.modules.orders.schemas import OrderResponseSchema
from app.modules.restaurants.models import Restaurant
from app.modules.riders.models import Rider
from app.modules.riders.schemas import (
    AvailableOrderSchema,
    LocationUpdateSchema,
    OnlineStatusSchema,
    RiderProfileResponseSchema,
)
from app.modules.riders.services import (
    get_rider_for_current_user,
    toggle_rider_online_status,
    update_rider_location,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/rider", tags=["rider"])


# dependency- fetches the rider profile
async def get_current_rider(
    current_user: Annotated[User, Depends(require_roles(UserRole.RIDER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Rider:
    """
    Shared dependency used by every rider-facing route.
    Fetches the Rider profile, raises 404 if none exists,
    raises 403 if the account is suspended.
    """
    return await get_rider_for_current_user(current_user.id, db)


# Profile
@router.get("/me", response_model=RiderProfileResponseSchema)
async def get_my_rider_profile(
    rider: Annotated[Rider, Depends(get_current_rider)],
):
    """Rider's own profile — no DB query needed, already fetched by dependency."""
    return rider


#  Availability toggle
@router.patch("/status", response_model=RiderProfileResponseSchema)
async def set_online_status(
    data: OnlineStatusSchema,
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Go online (ready to receive orders) or offline.
    NOTE-Cannot go offline while a delivery is in progress.
    """
    return await toggle_rider_online_status(rider, data.go_online, db)


# Available orders


@router.get("/orders/available", response_model=list[AvailableOrderSchema])
async def get_available_orders(
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
    radius_km: float = Query(default=5.0, ge=1.0, le=20.0),
):
    """
    Returns READY_FOR_PICKUP orders near the rider's current location,
    sorted by proximity. The rider uses this to see what's available and
    proactively accept, separate from push notifications.

    Note: not returning the full delivery address — only the
    general area. Full address is in the order detail route, which the
    rider can access only after accepting.
    """
    if not rider.is_online:
        raise HTTPException(
            status_code=400,
            detail="You must be online to view available orders",
        )

    if rider.current_latitude is None or rider.current_longitude is None:
        raise HTTPException(
            status_code=400,
            detail="Location not available. Update your location first.",
        )

    # Find restaurants with READY_FOR_PICKUP orders near the rider
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .join(Restaurant, Order.restaurant_id == Restaurant.id)
        .where(
            Order.status == OrderStatus.READY_FOR_PICKUP,
            Order.rider_id.is_(None),  # not yet assigned to anyone
        )
    )
    available_orders = result.scalars().all()

    if not available_orders:
        return []

    # Build response with distance info
    response = []
    for order in available_orders:
        # Get restaurant coordinates for this order
        restaurant = await db.get(Restaurant, order.restaurant_id)
        if not restaurant or restaurant.latitude is None:
            continue

        from app.modules.riders.services import haversine_km

        distance = haversine_km(
            float(rider.current_latitude),
            float(rider.current_longitude),
            float(restaurant.latitude),
            float(restaurant.longitude),
        )

        if distance > radius_km:
            continue

        response.append(
            AvailableOrderSchema(
                order_id=order.id,
                restaurant_name=order.restaurant_name,
                restaurant_latitude=restaurant.latitude,
                restaurant_longitude=restaurant.longitude,
                delivery_area=(
                    order.delivery_address.split(",")[-3].strip()
                    if order.delivery_address
                    else "Unknown area"
                ),
                delivery_fee=order.delivery_fee,
                estimated_distance_km=round(distance, 2),
                item_count=len(order.items),
                placed_at=order.placed_at,
            )
        )

    response.sort(key=lambda o: o.estimated_distance_km or 999)
    return response


# Location updates 
@router.patch("/location", status_code=204)
async def update_location(
    data: LocationUpdateSchema,
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    High-frequency endpoint — called every 3-5 seconds by the rider app.
    Returns 204 No Content intentionally — as no response body needed
    on a location ping to minimise response payload on every call.
    """
    await update_rider_location(rider, data.latitude, data.longitude, db)

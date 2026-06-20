import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    RiderLocationResponseSchema,
    RiderProfileResponseSchema,
)
from app.modules.riders.services import (
    assign_rider_to_order,
    get_rider_for_current_user,
    mark_order_delivered,
    mark_order_picked_up,
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
    shared dependency used by all rider facing endpoints.
    fetches the rider object, if not found returns 404 and
    403 if the account is suspended

    """
    return await get_rider_for_current_user(current_user.id, db)


# Profile
@router.get("/me", response_model=RiderProfileResponseSchema)
async def get_my_rider_profile(
    rider: Annotated[Rider, Depends(get_current_rider)],
):
    """Rider's me route to fetch the profile"""
    return rider


#  Availability toggle
@router.patch("/status", response_model=RiderProfileResponseSchema)
async def set_online_status(
    data: OnlineStatusSchema,
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Route to toggle the rider status between online and offline
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

    Returns the orders with the status READY_FOR_PICKUP near the rider sorted by the distance.

    Note: not returning the full address of the delivery, showing just the approx area
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
@router.patch(
    "/location",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_location(
    data: LocationUpdateSchema,
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Route called by the rider app frequenty(every 3-5 sec) to update the riders current location.
    Returning 204 as no body is needed and to make the route light for frequent calls
    """
    await update_rider_location(rider, data.latitude, data.longitude, db)


# Order lifecycle


@router.post("/orders/{order_id}/accept", response_model=OrderResponseSchema)
async def accept_order(
    order_id: uuid.UUID,
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Endpoint used by the rider to accept an order.
    using 'select for update' to enforce to prevent two rider accepting same order simultaneously
    """
    if not rider.is_online or not rider.is_available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must be online and available to accept orders",
        )

    return await assign_rider_to_order(order_id, rider, db)


@router.get("/orders/active", response_model=OrderResponseSchema)
async def get_active_order(
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Returns riders current active orders (if any).
    A rider can have at most one active order
    """
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.payment))
        .where(
            Order.rider_id == rider.id,
            Order.status.in_(
                [
                    OrderStatus.RIDER_ASSIGNED,
                    OrderStatus.OUT_FOR_DELIVERY,
                ]
            ),
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="No active order found",
        )

    return order


@router.post("/orders/{order_id}/pickup", response_model=OrderResponseSchema)
async def confirm_pickup(
    order_id: uuid.UUID,
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Route used by the rider to confirm the order pick up from the restaurant
    changes the order status from: RIDER_ASSIGNED -> OUT_FOR_DELIVERY.
    """
    return await mark_order_picked_up(order_id, rider, db)


@router.post("/orders/{order_id}/delivered", response_model=OrderResponseSchema)
async def confirm_delivery(
    order_id: uuid.UUID,
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Rider confirms delivery.
    -changes order status from: Order -> DELIVERED
    -for COD orders, changes the payment status: Payment -> PAID
    - Rider becomes available for new orders
    - total_deliveries increments
    """
    return await mark_order_delivered(order_id, rider, db)


@router.get("/orders/history", response_model=list[OrderResponseSchema])
async def get_delivery_history(
    rider: Annotated[Rider, Depends(get_current_rider)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Past completed deliveries of a rider sorted by newest first, paginated."""
    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.payment),
            selectinload(Order.items),
        )
        .where(
            Order.rider_id == rider.id,
            Order.status == OrderStatus.DELIVERED,
        )
        .order_by(Order.delivered_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


# route called by the customers front end to fetch riders location
@router.get("/{order_id}/rider-location", response_model=RiderLocationResponseSchema)
async def get_order_rider_location(
    order_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Return the assigned rider's latest location for order tracking.

    The location is only available once a rider has been assigned to the
    order, and can only be viewed by the customer who placed the order.
    """

    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status not in (OrderStatus.RIDER_ASSIGNED, OrderStatus.OUT_FOR_DELIVERY):
        raise HTTPException(
            status_code=400,
            detail="Rider location is not available for this order yet",
        )

    if not order.rider_id:
        raise HTTPException(status_code=404, detail="No rider assigned to this order")

    result = await db.execute(
        select(Rider)
        .options(selectinload(Rider.user))
        .where(Rider.id == order.rider_id)
    )
    rider = result.scalar_one_or_none()

    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")

    return RiderLocationResponseSchema(
        rider_first_name=rider.user.full_name.split()[0],
        rider_profile_image=rider.profile_image,
        vehicle_type=rider.vehicle_type,
        current_latitude=rider.current_latitude,
        current_longitude=rider.current_longitude,
        last_location_update=rider.last_location_update,
    )

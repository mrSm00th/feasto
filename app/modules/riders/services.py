import math
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.modules.notifications.models import NotificationType
from app.modules.notifications.services import create_notification
from app.modules.orders.models import CancellationReason, Order, OrderStatus
from app.modules.payments.models import PaymentStatus
from app.modules.riders.models import Rider, RiderProfileStatus

# Constants

EARTH_RADIUS_KM = 6371.0
DEFAULT_SEARCH_RADIUS_KM = 5.0  # initial search radius
MAX_SEARCH_RADIUS_KM = 15.0  # expand the search if no riders found nearby
CANDIDATE_POOL_SIZE = 5  # notify top N closest riders simultaneously
RIDER_ACCEPTANCE_TIMEOUT_SECONDS = 30  # rider has this long to accept before auto skip


# creating a box around the restaurant to filter out riders
def _bounding_box(
    lat: float, lon: float, radius_km: float
) -> tuple[float, float, float, float]:
    """
    Return (min_lat, max_lat, min_lon, max_lon) for a square bounding box
    around (lat, lon) of size radius_km.

    Over estimates the rider around the corners of actual circle

    1 degree latitude ≈ 111km everywhere.
    1 degree longitude ≈ 111km * cos(lat) — using this formula as long. shrinks around poles.
    """
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))
    return (
        lat - lat_delta,
        lat + lat_delta,
        lon - lon_delta,
        lon + lon_delta,
    )


# Haversine distance - for exact filtering after the bounding box approximation


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate the great-circle distance in kilometres between two points
    on Earth using the Haversine formula. This is more accurate than
    Euclidean distance for geographic coordinates, especially over longer
    distances where the Earth's curvature matters.

    """
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


# Core matching logic


async def find_nearby_riders(
    restaurant_lat: float,
    restaurant_lon: float,
    db: AsyncSession,
    radius_km: float = DEFAULT_SEARCH_RADIUS_KM,
) -> list[tuple[Rider, float]]:
    """
    Find available riders within radius_km of the pickup point.

    Returns a list of (rider, distance_km) tuples sorted by:
        1. Distance ascending (closest first — primary sort)
        2. avg_rating descending (higher rated first — tiebreaker)

    Two-level approach:
        Level 1: Using Bounding Box- a db level approximate filtering
                that over estimates the riders within the specified range
                but filters most of the riders

        Level 2: Python-level Haversine calculation on the small
                 candidate set returned by level 1.

    Stale-location guard: riders whose last_location_update is older
    than 5 minutes are treated as effectively offline regardless of
    their is_online flag.
    This handles app crashes without clean logout.
    """
    staleness_cutoff = datetime.now(UTC) - timedelta(minutes=5)
    min_lat, max_lat, min_lon, max_lon = _bounding_box(
        restaurant_lat, restaurant_lon, radius_km
    )

    # level-1: performs the bound box
    result = await db.execute(
        select(Rider).where(
            Rider.is_online.is_(True),
            Rider.is_available.is_(True),
            Rider.status == RiderProfileStatus.ACTIVE,
            Rider.current_latitude.isnot(None),
            Rider.current_longitude.isnot(None),
            Rider.last_location_update >= staleness_cutoff,
            Rider.current_latitude.between(min_lat, max_lat),
            Rider.current_longitude.between(min_lon, max_lon),
        )
    )
    candidates = result.scalars().all()

    # Level-2: precise Haversine filter
    riders_with_distance: list[tuple[Rider, float]] = []
    for rider in candidates:
        distance = haversine_km(
            restaurant_lat,
            restaurant_lon,
            float(rider.current_latitude),
            float(rider.current_longitude),
        )
        if distance <= radius_km:
            riders_with_distance.append((rider, distance))

    # Sort: closest first, higher rated as tiebreaker
    riders_with_distance.sort(key=lambda t: (t[1], -float(t[0].avg_rating)))
    return riders_with_distance


async def dispatch_order_to_riders(
    order: Order,
    db: AsyncSession,
) -> bool:
    """
    Find nearby riders and notify them of a new delivery opportunity.
    Returns True if at least one rider was notified, False if no riders
    were found (triggers fallback: expand radius or mark unserviceable).

    This function only NOTIFIES — it does not assign. Assignment happens
    when the rider explicitly accepts via POST /rider/orders/{id}/accept.

    """
    restaurant = await db.get(
        type(order.restaurant),  # avoids importing Restaurant directly
        order.restaurant_id,
    )
    if not restaurant or restaurant.latitude is None:
        return False

    riders_with_distance = await find_nearby_riders(
        float(restaurant.latitude),
        float(restaurant.longitude),
        db,
    )

    if not riders_with_distance:
        # Expand radius and try once more
        riders_with_distance = await find_nearby_riders(
            float(restaurant.latitude),
            float(restaurant.longitude),
            db,
            radius_km=MAX_SEARCH_RADIUS_KM,
        )

    if not riders_with_distance:
        return False

    # Notify top N candidates — they race to accept
    top_candidates = riders_with_distance[:CANDIDATE_POOL_SIZE]

    for rider, distance_km in top_candidates:
        await create_notification(
            user_id=rider.user_id,
            type=NotificationType.RIDER_ASSIGNED,
            reference_id=order.id,
            title="New Delivery Available",
            content=(
                f"Pickup from {order.restaurant_name} — "
                f"{distance_km:.1f}km away. ₹{order.delivery_fee} earnings."
            ),
            db=db,
        )

    return True


async def assign_rider_to_order(
    order_id: uuid.UUID,
    rider: Rider,
    db: AsyncSession,
) -> Order:
    """
    Atomically assign a rider to an order.

    Uses SELECT FOR UPDATE to lock the order row for the duration of
    this transaction. If two riders accept simultaneously:
        - First one acquires the lock, sees status=READY_FOR_PICKUP,
          proceeds with assignment.
        - Second one acquires the lock after first commits, sees
          status=RIDER_ASSIGNED, raises 409 — order already taken.

    """
    # SELECT FOR UPDATE — locks this row until the transaction ends
    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # By the time we reach here (after acquiring the lock), another
    # rider may have already been assigned — check the current state
    if order.status != OrderStatus.READY_FOR_PICKUP:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order has already been assigned to another rider",
        )

    now = datetime.now(UTC)

    # Assign the rider to the order
    order.rider_id = rider.id
    order.status = OrderStatus.RIDER_ASSIGNED
    order.rider_assigned_at = now

    # Mark rider as no longer available for new orders
    rider.is_available = False

    await create_notification(
        user_id=order.user_id,
        type=NotificationType.RIDER_ASSIGNED,
        reference_id=order.id,
        title="Rider Assigned",
        content=f"Your rider is on the way to pick up your order",
        db=db,
    )

    await db.commit()
    await db.refresh(order)
    return order


async def get_rider_for_current_user(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Rider:
    """
    Fetch the Rider profile for the currently authenticated user.
    Used as the base ownership check in all rider-facing routes —
    same principle as 'get_order_owned_by_restaurant'.
    """
    result = await db.execute(select(Rider).where(Rider.user_id == user_id))
    rider = result.scalar_one_or_none()

    if not rider:
        raise HTTPException(
            status_code=404,
            detail="Rider profile not found",
        )

    if rider.status == RiderProfileStatus.SUSPENDED:
        raise HTTPException(
            status_code=403,
            detail="Your rider account has been suspended",
        )

    return rider


async def toggle_rider_online_status(
    rider: Rider,
    go_online: bool,
    db: AsyncSession,
) -> Rider:
    """
    Rider taps the online/offline toggle in their app.

    Going online: sets is_online=True, is_available=True
    Going offline: sets is_online=False, is_available=False
        — a rider mid-delivery cannot go offline until they
          deliver the current order.
    """
    if not go_online:
        # Prevent going offline mid-delivery
        result = await db.execute(
            select(Order).where(
                Order.rider_id == rider.id,
                Order.status.in_(
                    [
                        OrderStatus.RIDER_ASSIGNED,
                        OrderStatus.OUT_FOR_DELIVERY,
                    ]
                ),
            )
        )
        active_order = result.scalar_one_or_none()
        if active_order:
            raise HTTPException(
                status_code=409,
                detail="Cannot go offline while an active delivery is in progress",
            )

    rider.is_online = go_online
    rider.is_available = go_online

    await db.commit()
    await db.refresh(rider)
    return rider

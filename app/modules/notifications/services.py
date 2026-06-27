import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification, NotificationType
from app.modules.orders.models import Order
from app.modules.realtime.connection_manager import manager
from app.modules.restaurants.services import get_restaurant_with_owner


async def create_notification(
    user_id: uuid.UUID,  # the restaurant owner's id
    reference_id: uuid.UUID,  # the order id
    db: AsyncSession,
    title: str,
    content: str,
    type: NotificationType,
):

    notification = Notification(
        user_id=user_id,
        type=type,
        reference_id=reference_id,
        title=title,
        content=content,
    )

    db.add(notification)

    return notification  # only addining the notification in db,
    # will committed by caller function


# These two functions work collectively
# creates a notification -> stores it and if the owner is up
# pushed the notification through websocket


async def add_order_notification(order: Order, db: AsyncSession):

    restaurant = await get_restaurant_with_owner(order.restaurant_id, db)

    # Layer 1 — persistent record
    notification = await create_notification(
        user_id=restaurant.owner_id,
        type=NotificationType.ORDER_PLACED,
        reference_id=order.id,
        title="New Order Received",
        content=f"Order #{str(order.id)[:8]} — ₹{order.total_amount}",
        db=db,
    )

    return notification


# NOTE: we're just sending the data to the browser of the owner dashboard
# the dashboard front end decided what to do
async def push_new_order_to_restaurant(order: Order, db: AsyncSession):

    restaurant = await get_restaurant_with_owner(order.restaurant_id, db)

    # Layer 2 — real-time push (if owner's dashboard is open)
    # creating the json response(dict type layered response)
    await manager.send_to(
        key=order.restaurant_id,
        message={
            "type": "new_order",
            "order_id": str(order.id),
            "total_amount": str(order.total_amount),
            "items_count": len(order.items),
            "created_at": order.created_at.isoformat(),
        },
    )

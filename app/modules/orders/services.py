import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.orders.models import Order, OrderItem, OrderStatus
from app.modules.payments.models import Payment, PaymentProvider, PaymentStatus
from app.modules.realtime.connection_manager import manager
from app.modules.restaurants.models import Restaurant
from app.modules.users.models import Notification, NotificationType


async def create_order_from_cart(
    user,
    restaurant,
    address,
    address_snapshot: str,
    special_instructions: str | None,
    subtotal: Decimal,
    delivery_fee: Decimal,
    tax_amount: Decimal,
    total_amount: Decimal,
    payment_method: PaymentProvider,
    db: AsyncSession,
    cart,
    menu_item_map: dict,
):
    order = Order(
        user_id=user.id,
        restaurant_id=restaurant.id,
        restaurant_name=restaurant.name,
        address_id=address.id,
        delivery_address=address_snapshot,
        delivery_latitude=address.latitude,
        delivery_longitude=address.longitude,
        customer_name=user.full_name,
        customer_phone=user.phone_number,
        customer_email=user.email,
        status=OrderStatus.AWAITING_PAYMENT,
        special_instructions=special_instructions,
        subtotal=subtotal,
        delivery_fee=delivery_fee,
        tax_amount=tax_amount,
        discount_amount=Decimal("0.00"),
        total_amount=total_amount,
        payment_method=payment_method,
        # placed_at is None here — set when payment confirms
        # but for cod we'll set it later belong in this same func
    )

    db.add(order)
    await db.flush()  # get order.id

    for cart_item in cart.items:
        menu_item = menu_item_map[cart_item.menu_item_id]
        order_item = OrderItem(
            order_id=order.id,
            menu_item_id=menu_item.id,
            item_name=menu_item.name,
            item_description=menu_item.description,
            quantity=cart_item.quantity,
            item_price=menu_item.price,
            total_price=menu_item.price * cart_item.quantity,
        )
        db.add(order_item)

    payment = Payment(
        order_id=order.id,
        provider=payment_method,
        amount=total_amount,
        status=PaymentStatus.PENDING,
    )
    db.add(payment)

    # for COD — cart cleared in the same transaction
    if payment_method == PaymentProvider.COD:

        order.status = OrderStatus.PLACED
        order.placed_at = datetime.now(UTC)

        notification = await add_order_notification(order, db)

        db.add(notification)
        await db.delete(cart)

    # a single commit for everything above
    await db.commit()

    # Reloading with  relationships for the response schema
    # and for the push

    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.items),
            selectinload(Order.payment),
        )
        .where(Order.id == order.id)
    )

    order = result.scalar_one()

    if order.payment_method == PaymentProvider.COD:

        await push_new_order_to_restaurant(order, db)

    return order


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


async def get_restaurant_with_owner(
    restaurant_id: uuid.UUID,
    db: AsyncSession,
):

    result = await db.execute(
        select(Restaurant)
        .options(selectinload(Restaurant.owner))
        .where(Restaurant.id == restaurant_id)
    )

    restaurant = result.scalar_one_or_none()

    if not restaurant:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Restaurant not found for this owner",
        )

    return restaurant


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
    await manager.send_to_restaurant(
        restaurant_id=order.restaurant_id,
        message={
            "type": "new_order",
            "order_id": str(order.id),
            "total_amount": str(order.total_amount),
            "items_count": len(order.items),
            "created_at": order.created_at.isoformat(),
        },
    )


async def get_restaurant_owned_by(
    restaurant_id: uuid.UUID,
    current_user_id: uuid.UUID,
    db: AsyncSession,
):

    result = await db.execute(
        select(Restaurant).where(
            Restaurant.id == restaurant_id,
            Restaurant.owner_id == current_user_id,
        )
    )

    restaurant = result.scalar_one_or_none()

    if not restaurant:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="restaurant not found",
        )

    return restaurant


async def get_order_owned_by_restaurant(
    order_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
):

    result = await db.execute(
        select(Order)
        .join(Restaurant)
        .where(Restaurant.owner_id == user_id, Order.id == order_id)
    )

    order = result.scalars().first()

    if not order:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="order not found",
        )

    return order

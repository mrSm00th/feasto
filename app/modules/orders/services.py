import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.modules.notifications.services import (
    add_order_notification,
    push_new_order_to_restaurant,
)
from app.modules.orders.models import Order, OrderItem, OrderStatus
from app.modules.orders.tasks import check_order_timeout
from app.modules.payments.models import Payment, PaymentProvider, PaymentStatus
from app.modules.realtime.connection_manager import manager
from app.modules.restaurants.models import Restaurant


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

    # NOTE:
    # Schedule the timeout check — countdown is in seconds
    check_order_timeout.apply_async(
        args=[str(payment.order.id)],
        countdown=settings.order_response_timeout_minutes * 60,
    )

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


async def get_order_owned_by_restaurant(
    order_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
):

    result = await db.execute(
        select(Order)
        .join(Restaurant)
        .options(selectinload(Order.items), selectinload(Order.payment))
        .where(Restaurant.owner_id == user_id, Order.id == order_id)
    )

    order = result.scalars().first()

    if not order:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="order not found",
        )

    return order

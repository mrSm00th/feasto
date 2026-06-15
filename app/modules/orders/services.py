import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.orders.models import Order, OrderItem, OrderStatus
from app.modules.payments.models import Payment, PaymentProvider, PaymentStatus
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
        await db.delete(cart)

    await db.commit()

    # Reloading with  relationships for the response schema
    result = await db.execute(
        select(Order)
        .options(
            selectinload(Order.items),
            selectinload(Order.payment),
        )
        .where(Order.id == order.id)
    )
    return result.scalar_one()


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
        type=NotificationType.ORDER_PLACED,
        reference_id=reference_id,
        title=title,
        content=content,
    )

    db.add(notification)

    return notification  # only addining the notification in db,
    # will committed by caller function

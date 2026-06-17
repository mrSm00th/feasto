# orders/customer_router.py

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.orders.models import Order
from app.modules.orders.schemas import IncomingOrdersResponseSchema, OrderResponseSchema
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=IncomingOrdersResponseSchema)
async def get_my_orders(
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Order history — all of this customer's orders, newest first."""
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.payment))
        .where(Order.user_id == current_user.id)
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()

    return IncomingOrdersResponseSchema(total=len(orders), orders=orders)


@router.get("/{order_id}", response_model=OrderResponseSchema)
async def get_order_status(
    order_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.payment))
        .where(
            Order.id == order_id,
            Order.user_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return order

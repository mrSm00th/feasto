import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import require_roles
from app.db.database import get_db
from app.modules.carts.models import Cart, CartItem
from app.modules.carts.schemas import (
    CartAddItemSchema,
    CartItemRemoveSchema,
    CartItemResponseSchema,
    CartResponseSchema,
)
from app.modules.menus.models import MenuItem, MenuItemStatus
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/cart", tags=["cart"])


# ADD or UPDATE an item in the cart
@router.post(
    "/items",
    status_code=status.HTTP_200_OK,
    response_model=CartResponseSchema,
    description=(
        "Uses **set semantics** — `quantity` is the desired final count, not a delta. "
        "To increase from 2 → 3, send `quantity: 3`. "
        "Sending an existing item overwrites its quantity. "
        "Sending items from a different restaurant clears the current cart first."
    ),
)
async def add_item_to_cart(
    data: CartAddItemSchema,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Validate all menu items BEFORE accessing the cart
    requested_ids = [entry.menu_item_id for entry in data.items]

    result = await db.execute(select(MenuItem).where(MenuItem.id.in_(requested_ids)))
    menu_items = result.scalars().all()
    menu_item_map = {item.id: item for item in menu_items}

    for entry in data.items:
        item = menu_item_map.get(entry.menu_item_id)

        if not item:
            raise HTTPException(
                status_code=404, detail=f"Menu item {entry.menu_item_id} not found"
            )
        if item.restaurant_id != data.restaurant_id:
            raise HTTPException(
                status_code=400, detail="Item does not belong to this restaurant"
            )
        if item.status != MenuItemStatus.ACTIVE or not item.is_available:
            raise HTTPException(
                status_code=400, detail=f"'{item.name}' is not available"
            )

    # Fetch existing cart
    result = await db.execute(select(Cart).where(Cart.user_id == current_user.id))
    existing_cart = result.scalar_one_or_none()

    # If cart belongs to a different restaurant, clear it
    if existing_cart and existing_cart.restaurant_id != data.restaurant_id:
        await db.delete(existing_cart)
        await db.flush()
        existing_cart = None

    if existing_cart is None:
        existing_cart = Cart(
            user_id=current_user.id,
            restaurant_id=data.restaurant_id,
        )
        db.add(existing_cart)
        await db.flush()

    # Fetch existing cart items for upsert
    result = await db.execute(
        select(CartItem).where(CartItem.cart_id == existing_cart.id)
    )
    existing_items = result.scalars().all()
    existing_item_map = {item.menu_item_id: item for item in existing_items}

    # Upsert each item
    for entry in data.items:
        menu_item = menu_item_map[entry.menu_item_id]

        if entry.menu_item_id in existing_item_map:
            cart_item = existing_item_map[entry.menu_item_id]
            cart_item.quantity = entry.quantity
            cart_item.item_price = menu_item.price  # re-snapshot in case price changed
            cart_item.item_name = menu_item.name
        else:
            cart_item = CartItem(
                cart_id=existing_cart.id,
                menu_item_id=entry.menu_item_id,
                item_name=menu_item.name,
                quantity=entry.quantity,
                item_price=menu_item.price,
            )
            db.add(cart_item)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update cart")

    # Reload full cart with items after commit
    result = await db.execute(
        select(Cart)
        .options(selectinload(Cart.items))
        .where(Cart.id == existing_cart.id)
    )
    existing_cart = result.scalars().first()

    items = []
    total_price = Decimal("0.0")
    for item in existing_cart.items:
        items.append(
            CartItemResponseSchema(
                id=item.id,
                menu_item_id=item.menu_item_id,  # FIX: include menu_item_id in response
                name=item.item_name,
                quantity=item.quantity,
                price=item.item_price,
            )
        )
        total_price += item.item_price * item.quantity

    return CartResponseSchema(
        cart_id=existing_cart.id,
        restaurant_id=existing_cart.restaurant_id,
        items=items,
        total_price=total_price,
    )


# GET current user's cart
@router.get("", response_model=CartResponseSchema)
async def get_cart(
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Cart)
        .options(selectinload(Cart.items))
        .where(Cart.user_id == current_user.id)
    )
    cart = result.scalars().first()

    if not cart:
        return CartResponseSchema(
            items=[],
            total_price=Decimal("0.0"),
            restaurant_id=None,
        )

    cart_menu_item_ids = [item.menu_item_id for item in cart.items]

    result = await db.execute(
        select(MenuItem).where(
            MenuItem.restaurant_id == cart.restaurant_id,
            MenuItem.id.in_(cart_menu_item_ids),
        )
    )
    menu_items = result.scalars().all()
    menu_item_map = {item.id: item for item in menu_items}

    total_price = Decimal("0.0")
    items = []
    for cart_item in cart.items:
        menu_item = menu_item_map[cart_item.menu_item_id]
        items.append(
            CartItemResponseSchema(
                id=cart_item.id,
                menu_item_id=cart_item.menu_item_id,  # FIX: include menu_item_id in response
                name=menu_item.name,
                quantity=cart_item.quantity,
                price=menu_item.price,
            )
        )
        total_price += menu_item.price * cart_item.quantity

    return CartResponseSchema(
        cart_id=cart.id,
        restaurant_id=cart.restaurant_id,
        items=items,
        total_price=total_price,
    )


# PATCH /cart/items/{cart_item_id} — reduce quantity by N, remove if hits 0
@router.patch(
    "/items/{cart_item_id}",
    status_code=status.HTTP_200_OK,
    response_model=CartResponseSchema,
    description=(
        "Send the quantity to reduce. "
        "To go from 3 → 2, send `quantity: 1. "
        "If reduced quantity reaches 0, the item is removed. "
        "If the cart becomes empty, it is also deleted."
    ),
)
async def reduce_cart_item_quantity(
    cart_item_id: uuid.UUID,
    data: CartItemRemoveSchema,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(CartItem)
        .options(selectinload(CartItem.cart))
        .where(CartItem.id == cart_item_id)
    )
    cart_item = result.scalar_one_or_none()

    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    if cart_item.cart.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your cart")

    cart = cart_item.cart

    if data.quantity > cart_item.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot remove {data.quantity} units — only {cart_item.quantity} in cart",
        )

    cart_deleted = False

    if data.quantity == cart_item.quantity:
        await db.delete(cart_item)
        await db.flush()  # FIX: flush before counting so deleted row is excluded

        result = await db.execute(
            select(func.count(CartItem.id)).where(CartItem.cart_id == cart.id)
        )
        remaining_count = result.scalar()

        if remaining_count == 0:  # FIX: 0 not 1, because flush already removed the row
            await db.delete(cart)
            cart_deleted = True
    else:
        cart_item.quantity -= data.quantity

    await db.commit()

    if cart_deleted:
        return CartResponseSchema(
            cart_id=None,
            restaurant_id=None,
            items=[],
            total_price=Decimal("0.0"),
        )

    result = await db.execute(
        select(Cart).options(selectinload(Cart.items)).where(Cart.id == cart.id)
    )
    cart = result.scalars().first()

    items = []
    total_price = Decimal("0.0")
    for ci in cart.items:
        items.append(
            CartItemResponseSchema(
                id=ci.id,
                menu_item_id=ci.menu_item_id,
                name=ci.item_name,
                quantity=ci.quantity,
                price=ci.item_price,
            )
        )
        total_price += ci.item_price * ci.quantity

    return CartResponseSchema(
        cart_id=cart.id,
        restaurant_id=cart.restaurant_id,
        items=items,
        total_price=total_price,
    )


# DELETE /cart/items/{cart_item_id} — remove item entirely regardless of quantity
@router.delete(
    "/items/{cart_item_id}",
    status_code=status.HTTP_200_OK,
    response_model=CartResponseSchema,
)
async def remove_cart_item(
    cart_item_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(CartItem)
        .options(selectinload(CartItem.cart))
        .where(CartItem.id == cart_item_id)
    )
    cart_item = result.scalar_one_or_none()

    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    if cart_item.cart.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your cart")

    cart = cart_item.cart

    await db.delete(cart_item)
    await db.flush()  # push DELETE to DB so count is accurate

    result = await db.execute(
        select(func.count(CartItem.id)).where(CartItem.cart_id == cart.id)
    )
    remaining_count = result.scalar()

    cart_deleted = False
    if remaining_count == 0:
        await db.delete(cart)
        cart_deleted = True

    await db.commit()

    if cart_deleted:
        return CartResponseSchema(
            cart_id=None,
            restaurant_id=None,
            items=[],
            total_price=Decimal("0.0"),
        )

    result = await db.execute(
        select(Cart).options(selectinload(Cart.items)).where(Cart.id == cart.id)
    )
    cart = result.scalars().first()

    items = []
    total_price = Decimal("0.0")
    for ci in cart.items:
        items.append(
            CartItemResponseSchema(
                id=ci.id,
                menu_item_id=ci.menu_item_id,
                name=ci.item_name,
                quantity=ci.quantity,
                price=ci.item_price,
            )
        )
        total_price += ci.item_price * ci.quantity

    return CartResponseSchema(
        cart_id=cart.id,
        restaurant_id=cart.restaurant_id,
        items=items,
        total_price=total_price,
    )


# DELETE /cart — clear the entire cart
@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def clear_cart(
    current_user: Annotated[User, Depends(require_roles(UserRole.CUSTOMER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Cart).where(Cart.user_id == current_user.id))
    cart = result.scalars().first()

    if not cart:  # guard against missing cart — db.delete(None) throws
        raise HTTPException(status_code=404, detail="No cart found")

    await db.delete(cart)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to clear cart")

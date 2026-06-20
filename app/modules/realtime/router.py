import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import WebSocketException

from app.core.auth import get_current_user_ws
from app.db.database import get_db
from app.modules.realtime.connection_manager import manager
from app.modules.restaurants.models import Restaurant
from app.modules.users.models import UserRole

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/restaurant/{restaurant_id}")
async def restaurant_feed(
    websocket: WebSocket,
    restaurant_id: uuid.UUID,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await get_current_user_ws(token, db)
    except Exception:
        await websocket.accept()
        await websocket.close(code=1008, reason="Invalid token")
        return

    if user.role != UserRole.RESTAURANT_OWNER:
        await websocket.accept()
        await websocket.close(code=1008, reason="Not a restaurant owner")
        return

    await manager.connect(restaurant_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(restaurant_id, websocket)


@router.websocket("/ws/rider")
async def rider_feed(
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Riders connect here (no path param needed — keyed by their own
    user_id) to receive NEW_DELIVERY_AVAILABLE pushes the instant
    dispatch_order_to_riders() fires, instead of waiting for the next
    poll of /rider/orders/available.
    """
    try:
        user = await get_current_user_ws(token, db)
    except Exception:
        await websocket.accept()
        await websocket.close(code=1008, reason="Invalid token")
        return

    if user.role != UserRole.RIDER:
        await websocket.accept()
        await websocket.close(code=1008, reason="Not a rider")
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)


@router.websocket("/ws/customer")
async def customer_feed(
    websocket: WebSocket,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Customer connects here (keyed by their own user_id) to receive
    live order status pushes — ORDER_CONFIRMED, RIDER_ASSIGNED,
    ORDER_PICKED_UP, ORDER_DELIVERED — as they happen, instead of
    polling GET /orders/{id}.
    """
    try:
        user = await get_current_user_ws(token, db)
    except Exception:
        await websocket.accept()
        await websocket.close(code=1008, reason="Invalid token")
        return

    if user.role != UserRole.CUSTOMER:
        await websocket.accept()
        await websocket.close(code=1008, reason="Not a customer")
        return

    await manager.connect(user.id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user.id, websocket)

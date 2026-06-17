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
async def restaurant_order_updates_ws(
    websocket: WebSocket,
    restaurant_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str = Query(...),  # JWT passed as query param as ws cant set custom headers
):
    # Verify the token belongs to the owner of this restaurant
    try:
        user = await get_current_user_ws(token, db)
    except WebSocketException as exc:
        # accept() before close() cause we need to send the error msg
        # if we dont accept client will see a generic connection failed
        await websocket.accept()
        await websocket.close(code=exc.code, reason=exc.reason)
        return

    if user.role != UserRole.RESTAURANT_OWNER:
        await websocket.accept()
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Not a restaurant owner"
        )
        return

    # verify user actually owns restaurant_id
    result = await db.execute(
        select(Restaurant).where(
            Restaurant.id == restaurant_id, Restaurant.owner_id == user.id
        )
    )

    restaurant = result.scalars().first()

    if not restaurant:
        await websocket.accept()
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Restaurant not found for this user",
        )
        return

    # accepting the ws and registering it
    await manager.connect(restaurant_id, websocket)

    try:
        while True:
            # Keep the connection alive — we don't expect the client
            # to send anything, but we must await something or the
            # connection closes immediately
            await websocket.receive_text()

    # when the client disconnects , this exception is raised automatically
    # this signals us that the connection is closed
    except WebSocketDisconnect:
        manager.disconnect(restaurant_id, websocket)

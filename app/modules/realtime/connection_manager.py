import uuid

from fastapi import WebSocket


class ConnectionManager:
    """
    Tracks active WebSocket connections, keyed by an arbitrary UUID —
    restaurant_id, user_id, or rider's user_id. The key's meaning is
    decided by the caller, this class acts as a connection registry.
    """

    def __init__(self):
        self.active_connections: dict[uuid.UUID, list[WebSocket]] = {}

    async def connect(self, key: uuid.UUID, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.setdefault(key, []).append(websocket)

    def disconnect(self, key: uuid.UUID, websocket: WebSocket):
        if key in self.active_connections:
            self.active_connections[key].remove(websocket)
            if not self.active_connections[key]:
                del self.active_connections[key]

    async def send_to(self, key: uuid.UUID, message: dict):
        for connection in self.active_connections.get(key, []):
            await connection.send_json(message)


manager = ConnectionManager()

import uuid

from fastapi import WebSocket


class ConnectionManager:
    """
    Stores WebSocket connections using a UUID as the key.

    The UUID can be a user, restaurant or rider id.
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

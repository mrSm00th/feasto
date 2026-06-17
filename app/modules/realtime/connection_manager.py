import uuid

from fastapi import WebSocket


class ConnectionManager:
    """
    Tracks active WebSocket connections, keyed by restaurant_id.

    One restaurant owner might have the dashboard open on multiple
    tabs/devices — so each restaurant_id maps to a LIST of connections.
    """

    # constructor - called for every instance of ConnectionManager
    # creates empty dictionary
    def __init__(self):
        self.active_connections: dict[uuid.UUID, list[WebSocket]] = {}

    # connecting and registering the websocket connection
    async def connect(
        self,
        restaurant_id: uuid.UUID,
        websocket: WebSocket,
    ):
        # accepting the upgrade request to webssocket
        await websocket.accept()

        if restaurant_id not in self.active_connections:

            self.active_connections[restaurant_id] = []

        self.active_connections[restaurant_id].append(websocket)

    async def disconnect(
        self,
        restaurant_id: uuid.UUID,
        websocket: WebSocket,
    ):

        if restaurant_id in self.active_connections:

            self.active_connections[restaurant_id].remove(websocket)

            # checking if no websocket exists for this restaurant_id
            # if yes - remove the key(restaurant_id)
            if not self.active_connections[restaurant_id]:

                del self.active_connections[restaurant_id]

    async def send_to_restaurant(self, restaurant_id: uuid.UUID, message: dict):
        """
        Push a message to all active connections for this restaurant.
        If the restaurant has no active connections, this silently
        does nothing — that's fine, Layer 1 (DB record) still exists.
        """
        connections = self.active_connections.get(restaurant_id, [])
        for connection in connections:
            await connection.send_json(message)


# Single shared instance across the app
manager = ConnectionManager()

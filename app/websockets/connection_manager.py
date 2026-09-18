import asyncio
from fastapi import WebSocket
from typing import Dict, List

class ConnectionManager:
    def __init__(self):
        # Maps a board_id to a list of active WebSocket connections
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, board_id: int):
        await websocket.accept()
        self.active_connections.setdefault(board_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, board_id: int):
        # Idempotent: a socket may already have been dropped by a failed broadcast
        connections = self.active_connections.get(board_id)
        if connections is None or websocket not in connections:
            return
        connections.remove(websocket)
        if not connections:
            del self.active_connections[board_id]

    async def broadcast(self, message: str, board_id: int):
        # Sends to everyone viewing this board concurrently, so one slow client can't delay
        # the rest, and a dead socket is dropped instead of aborting delivery to the others
        connections = list(self.active_connections.get(board_id, []))
        results = await asyncio.gather(
            *(connection.send_text(message) for connection in connections),
            return_exceptions=True,
        )
        for connection, result in zip(connections, results):
            if isinstance(result, Exception):
                self.disconnect(connection, board_id)

manager = ConnectionManager()

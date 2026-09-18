import asyncio
import contextlib
from dataclasses import dataclass
from fastapi import WebSocket
from typing import Dict, List

# Application close codes (4000-4999 are reserved for applications), so the client
# can tell "log in again" and "stop retrying" apart from a dropped network
CLOSE_UNAUTHENTICATED = 4401
CLOSE_NOT_A_MEMBER = 4403

@dataclass(eq=False)
class Connection:
    """One open socket and the user it belongs to. Compared by identity."""
    websocket: WebSocket
    user_id: int

class ConnectionManager:
    def __init__(self):
        # Maps a board_id to the connections this server instance holds for it
        self.active_connections: Dict[int, List[Connection]] = {}

    async def connect(self, websocket: WebSocket, board_id: int, user_id: int) -> Connection:
        await websocket.accept()
        connection = Connection(websocket, user_id)
        self.active_connections.setdefault(board_id, []).append(connection)
        return connection

    def disconnect(self, connection: Connection, board_id: int):
        # Idempotent: a connection may already have been dropped by a failed broadcast or a revocation
        connections = self.active_connections.get(board_id)
        if connections is None or connection not in connections:
            return
        connections.remove(connection)
        if not connections:
            del self.active_connections[board_id]

    async def broadcast(self, message: str, board_id: int):
        # Sends to everyone viewing this board concurrently, so one slow client can't delay
        # the rest, and a dead socket is dropped instead of aborting delivery to the others
        connections = list(self.active_connections.get(board_id, []))
        results = await asyncio.gather(
            *(connection.websocket.send_text(message) for connection in connections),
            return_exceptions=True,
        )
        for connection, result in zip(connections, results):
            if isinstance(result, Exception):
                self.disconnect(connection, board_id)

    async def disconnect_user(self, board_id: int, user_id: int, code: int):
        """Closes every socket this instance holds for a user on a board, e.g. after they are removed from it."""
        revoked = [c for c in self.active_connections.get(board_id, []) if c.user_id == user_id]
        for connection in revoked:
            self.disconnect(connection, board_id)
            with contextlib.suppress(Exception):
                await connection.websocket.close(code=code)

manager = ConnectionManager()

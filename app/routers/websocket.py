import asyncio
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.core.deps import get_membership, get_user_from_token
from app.db.session import SessionLocal
from app.websockets.connection_manager import manager
from app.services.broadcast_service import subscribe_to_channel

router = APIRouter()

# Application close codes (4000-4999 are reserved for applications), so the client
# can tell "log in again" and "stop retrying" apart from a dropped network
CLOSE_UNAUTHENTICATED = 4401
CLOSE_NOT_A_MEMBER = 4403

# Tracks active Redis subscriptions per board so we don't create duplicate listeners on the same server instance
redis_tasks = {}

def _refusal_code(token: Optional[str], board_id: int) -> Optional[int]:
    """Returns a close code if the connection must be refused, otherwise None."""
    # Synchronous DB work; called via the threadpool so it doesn't block the event loop
    if not token:
        return CLOSE_UNAUTHENTICATED
    with SessionLocal() as db:
        user = get_user_from_token(token, db)
        if user is None:
            return CLOSE_UNAUTHENTICATED
        if get_membership(db, board_id, user.id) is None:
            return CLOSE_NOT_A_MEMBER
    return None

@router.websocket("/ws/boards/{board_id}")
async def websocket_endpoint(websocket: WebSocket, board_id: int, token: Optional[str] = None):
    # Browsers can't set headers on WebSocket handshakes, so the JWT arrives as a query parameter
    refusal = await run_in_threadpool(_refusal_code, token, board_id)
    if refusal is not None:
        # Accept before closing: closing during the handshake turns into an HTTP 403,
        # which browsers only report as code 1006, indistinguishable from a network drop
        await websocket.accept()
        await websocket.close(code=refusal)
        return

    await manager.connect(websocket, board_id)

    # If this is the first user on this instance viewing this board (or the listener has
    # stopped unexpectedly), start listening to Redis
    if board_id not in redis_tasks or redis_tasks[board_id].done():
        redis_tasks[board_id] = asyncio.create_task(subscribe_to_channel(board_id))

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, board_id)

        # If no users are left on this instance for this board, cancel the Redis subscription to save resources
        if board_id not in manager.active_connections and board_id in redis_tasks:
            redis_tasks.pop(board_id).cancel()

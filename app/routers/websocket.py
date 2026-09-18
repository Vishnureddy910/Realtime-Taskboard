import asyncio
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from starlette.concurrency import run_in_threadpool

from app.core.deps import get_membership, get_user_from_token
from app.db.session import SessionLocal
from app.websockets.connection_manager import manager
from app.services.broadcast_service import subscribe_to_channel

router = APIRouter()

# Tracks active Redis subscriptions per board so we don't create duplicate listeners on the same server instance
redis_tasks = {}

def _is_board_member(token: Optional[str], board_id: int) -> bool:
    # Synchronous DB work; called via the threadpool so it doesn't block the event loop
    if not token:
        return False
    with SessionLocal() as db:
        user = get_user_from_token(token, db)
        return user is not None and get_membership(db, board_id, user.id) is not None

@router.websocket("/ws/boards/{board_id}")
async def websocket_endpoint(websocket: WebSocket, board_id: int, token: Optional[str] = None):
    # Browsers can't set headers on WebSocket handshakes, so the JWT arrives as a query parameter
    if not await run_in_threadpool(_is_board_member, token, board_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, board_id)

    # If this is the first user on this instance viewing this board, start listening to Redis
    if board_id not in redis_tasks:
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

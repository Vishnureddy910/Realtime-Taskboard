import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websockets.connection_manager import manager
from app.services.broadcast_service import subscribe_to_channel

router = APIRouter()

# Tracks active Redis subscriptions per board so we don't create duplicate listeners on the same server instance
redis_tasks = {}

@router.websocket("/ws/boards/{board_id}")
async def websocket_endpoint(websocket: WebSocket, board_id: int):
    await manager.connect(websocket, board_id)
    
    # If this is the first user on this instance viewing this board, start listening to Redis
    if board_id not in redis_tasks:
        redis_tasks[board_id] = asyncio.create_task(subscribe_to_channel(board_id))
        
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, board_id)
        
        # If no users are left on this instance for this board, cancel the Redis subscription to save resources
        if board_id not in manager.active_connections and board_id in redis_tasks:
            redis_tasks[board_id].cancel()
            del redis_tasks[board_id]
import json
import asyncio
from redis.asyncio import Redis
from app.core.config import settings
from app.websockets.connection_manager import manager

# Initialize Redis connection
redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)

async def publish_event(board_id: int, event_data: dict):
    """Publishes an event to the Redis channel for a specific board."""
    channel = f"board:{board_id}"
    message = json.dumps(event_data)
    await redis_client.publish(channel, message)

async def subscribe_to_channel(board_id: int):
    """Subscribes to a Redis channel and forwards messages to local WebSockets."""
    pubsub = redis_client.pubsub()
    channel = f"board:{board_id}"
    await pubsub.subscribe(channel)
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                # Forward the Redis message to all WebSockets connected to this specific instance
                await manager.broadcast(message["data"], board_id)
    except asyncio.CancelledError:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
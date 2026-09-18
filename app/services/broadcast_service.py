import json
import asyncio
import contextlib
import logging
from redis.asyncio import Redis
from redis.exceptions import RedisError
from app.core.config import settings
from app.websockets.connection_manager import manager

logger = logging.getLogger(__name__)

# Initialize Redis connection
redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)

RECONNECT_INITIAL_DELAY_SECONDS = 0.5
RECONNECT_MAX_DELAY_SECONDS = 30

# Sent to local clients after the listener recovers: events published while it was
# disconnected are gone (Pub/Sub is at-most-once), so clients must refetch the board
RESYNC_EVENT = json.dumps({"event": "resync"})

async def publish_event(board_id: int, event_data: dict):
    """Publishes an event to the Redis channel for a specific board."""
    channel = f"board:{board_id}"
    message = json.dumps(event_data)
    await redis_client.publish(channel, message)

async def subscribe_to_channel(board_id: int):
    """
    Subscribes to a board's Redis channel and forwards messages to local WebSockets.

    Supervised: if the Redis connection drops, it resubscribes with exponential
    backoff instead of dying silently and leaving this instance's clients without
    updates. Runs until cancelled (when the last local client leaves the board).
    """
    channel = f"board:{board_id}"
    delay = RECONNECT_INITIAL_DELAY_SECONDS
    recovering = False

    while True:
        pubsub = redis_client.pubsub()
        try:
            await pubsub.subscribe(channel)
            if recovering:
                logger.info("Resubscribed to %s", channel)
                await manager.broadcast(RESYNC_EVENT, board_id)
                recovering = False
            delay = RECONNECT_INITIAL_DELAY_SECONDS

            async for message in pubsub.listen():
                if message["type"] == "message":
                    # Forward the Redis message to all WebSockets connected to this specific instance
                    await manager.broadcast(message["data"], board_id)
        except (RedisError, OSError) as exc:
            logger.warning("Lost subscription to %s (%s); retrying in %.1fs", channel, exc, delay)
        finally:
            with contextlib.suppress(RedisError, OSError):
                await pubsub.aclose()

        # Reached only when the subscription ended without being cancelled
        recovering = True
        await asyncio.sleep(delay)
        delay = min(delay * 2, RECONNECT_MAX_DELAY_SECONDS)

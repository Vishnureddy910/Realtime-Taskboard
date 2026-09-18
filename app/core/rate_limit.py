from fastapi import Depends, HTTPException
from app.core.config import settings
from app.core.deps import get_current_user
from app.models.user import User
from app.services.broadcast_service import redis_client

class RateLimiter:
    """
    Fixed-window rate limiter keyed by user ID.

    Keyed by user rather than IP because behind Render's proxy every request
    arrives from the proxy's address, so all users would share one bucket.
    """

    def __init__(self, scope: str, limit: int, window_seconds: int):
        self.scope = scope
        self.limit = limit
        self.window_seconds = window_seconds

    async def __call__(self, current_user: User = Depends(get_current_user)):
        key = f"rate_limit:{self.scope}:{current_user.id}"

        # SET NX EX creates the counter and its TTL in one atomic step, and MULTI makes the
        # increment part of the same transaction. A separate INCR then EXPIRE could crash in
        # between and leave a counter that never expires, blocking the user permanently.
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.set(key, 0, ex=self.window_seconds, nx=True)
            pipe.incr(key)
            _, request_count = await pipe.execute()

        if request_count > self.limit:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait a minute before creating more tasks.",
            )

task_creation_rate_limit = RateLimiter(
    scope="tasks",
    limit=settings.TASK_RATE_LIMIT,
    window_seconds=settings.TASK_RATE_WINDOW_SECONDS,
)

from fastapi import HTTPException, Request
from app.services.broadcast_service import redis_client

async def rate_limit(request: Request):
    # We use the user's IP address to track them, but you could also use their JWT user ID
    client_ip = request.client.host
    key = f"rate_limit:tasks:{client_ip}"
    
    # Increment the counter for this IP
    request_count = await redis_client.incr(key)
    
    # If this is their first request, start the 60-second timer
    if request_count == 1:
        await redis_client.expire(key, 60)
        
    # If they exceed 5 requests within that 60 seconds, block them
    if request_count > 5:
        raise HTTPException(
            status_code=429, 
            detail="Too many requests. Please wait a minute before creating more tasks."
        )
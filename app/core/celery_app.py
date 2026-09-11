from celery import Celery
from app.core.config import settings

# We use Redis as both the broker (the queue) and the backend (where results are stored)
celery_app = Celery(
    "taskboard_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=['app.worker.tasks']  # Tells Celery where to look for tasks
)
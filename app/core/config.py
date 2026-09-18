import os

_DEV_SECRET_KEY = "dev-only-insecure-secret-key"


class Settings:
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/taskboard")

    # JWT Settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Redis Settings
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Rate limiting for task creation (per user)
    TASK_RATE_LIMIT: int = int(os.getenv("TASK_RATE_LIMIT", "5"))
    TASK_RATE_WINDOW_SECONDS: int = int(os.getenv("TASK_RATE_WINDOW_SECONDS", "60"))

    # Rate limiting for user search (per user), which slows down username enumeration
    USER_SEARCH_RATE_LIMIT: int = int(os.getenv("USER_SEARCH_RATE_LIMIT", "30"))
    USER_SEARCH_RATE_WINDOW_SECONDS: int = int(os.getenv("USER_SEARCH_RATE_WINDOW_SECONDS", "60"))

    def __init__(self):
        # Never silently fall back to a known signing key in production
        if not self.SECRET_KEY:
            if self.ENVIRONMENT == "production":
                raise RuntimeError("SECRET_KEY must be set in production")
            self.SECRET_KEY = _DEV_SECRET_KEY


settings = Settings()

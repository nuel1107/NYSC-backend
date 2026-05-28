from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database (Neon)
    DATABASE_URL: str  # postgres://user:pass@host/dbname

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 60 * 24        # 1 day
    JWT_REFRESH_EXPIRE_DAYS: int = 30

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"

    # File storage (Cloudflare R2 or any S3-compatible)
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_NAME: str = "triflow-media"
    S3_PUBLIC_BASE_URL: str = ""        # e.g. https://pub-xxx.r2.dev

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()

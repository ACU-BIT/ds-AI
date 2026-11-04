
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql://teledesk:teledesk@localhost:5432/teledesk"
    REDIS_URL: str = "redis://localhost:6379/0"

    MINIO_ENDPOINT: str = "http://localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "teledesk"

    GEMINI_API_KEY: str = ""
    GEMINI_CHAT_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"
    EMBED_DIM: int = 768

    ENCRYPTION_KEY: str = ""
    JWT_SECRET: str = "change-me"
    PUBLIC_BASE_URL: str = ""


settings = Settings()
FRONTEND_DIR = ROOT / "frontend"

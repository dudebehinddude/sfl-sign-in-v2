from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://sfl:sfl@localhost:5432/sfl"
    app_origin: str = Field(
        default="http://localhost:8080",
        validation_alias=AliasChoices("PUBLIC_ORIGIN", "APP_ORIGIN"),
    )
    session_hours: int = Field(default=12, ge=1, le=168)
    cookie_secure: bool = False
    app_port: int = Field(default=8080, ge=1, le=65535)

    @property
    def session_cookie(self) -> str:
        return f"sfl_session_{self.app_port}"

    avatar_max_bytes: int = 2 * 1024 * 1024
    s3_endpoint: str = "http://minio:9000"
    s3_bucket: str = "sfl-avatars"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    lab_timezone: str = "America/New_York"
    canvas_base_url: str = "https://instructure.charlotte.edu"
    canvas_api_token: str = ""
    canvas_course_id: str = ""
    canvas_sync_seconds: int = Field(
        default=3600,
        ge=30,
        validation_alias=AliasChoices("CANVAS_SYNC_INTERVAL_SECONDS", "CANVAS_SYNC_SECONDS"),
    )
    canvas_enrollment_url: str = ""
    sql_read_database_url: str = ""
    sql_write_database_url: str = ""
    sql_statement_timeout_ms: int = Field(default=5000, ge=100, le=30000)
    sql_max_rows: int = Field(default=1000, ge=1, le=1000)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        return value

    @property
    def psycopg_url(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    @property
    def canvas_configured(self) -> bool:
        return bool(self.canvas_api_token and self.canvas_course_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()

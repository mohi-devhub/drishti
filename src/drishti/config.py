from functools import lru_cache

from pydantic import AnyHttpUrl, Field, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="local", alias="DRISHTI_ENV")
    api_host: str = Field(default="0.0.0.0", alias="DRISHTI_API_HOST")
    api_port: int = Field(default=8000, alias="DRISHTI_API_PORT")
    web_origin: AnyHttpUrl = Field(default="http://localhost:3000", alias="DRISHTI_WEB_ORIGIN")
    extra_cors_origins: str = Field(default="", alias="DRISHTI_EXTRA_CORS_ORIGINS")
    allow_local_demo_auth: bool = Field(default=False, alias="DRISHTI_ALLOW_LOCAL_DEMO_AUTH")

    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    db_pool_size: int = Field(default=5, alias="DRISHTI_DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DRISHTI_DB_MAX_OVERFLOW")
    db_pool_timeout_seconds: int = Field(default=10, alias="DRISHTI_DB_POOL_TIMEOUT_SECONDS")
    db_pool_recycle_seconds: int = Field(default=1800, alias="DRISHTI_DB_POOL_RECYCLE_SECONDS")
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_publishable_key: str | None = Field(default=None, alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_anon_key: str | None = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")

    clerk_secret_key: str | None = Field(default=None, alias="CLERK_SECRET_KEY")
    clerk_jwt_issuer: str | None = Field(default=None, alias="CLERK_JWT_ISSUER")
    clerk_jwt_audience: str | None = Field(default=None, alias="CLERK_JWT_AUDIENCE")
    test_jwt_secret: str | None = Field(default=None, alias="DRISHTI_TEST_JWT_SECRET")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_chat_model: str = Field(default="gpt-5.2", alias="OPENAI_CHAT_MODEL")
    openai_cheap_model: str = Field(default="gpt-5-mini", alias="OPENAI_CHEAP_MODEL")

    logfire_token: str | None = Field(default=None, alias="LOGFIRE_TOKEN")
    logfire_service_name: str = Field(default="drishti-api", alias="LOGFIRE_SERVICE_NAME")

    transport_mode: str = Field(default="mock", alias="DRISHTI_TRANSPORT")
    shopify_webhook_secret: str | None = Field(default=None, alias="SHOPIFY_WEBHOOK_SECRET")

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        if self.environment != "local" and not self.database_url:
            raise ValueError("DATABASE_URL is required outside local environments")
        if not self.database_url:
            self.database_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/drishti"
        if self.environment != "local" and self.allow_local_demo_auth:
            raise ValueError("DRISHTI_ALLOW_LOCAL_DEMO_AUTH can only be enabled in local mode")
        if self.allow_local_demo_auth and not self.test_jwt_secret:
            raise ValueError("DRISHTI_TEST_JWT_SECRET is required when local demo auth is enabled")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

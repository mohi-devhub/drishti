from functools import lru_cache

from pydantic import AnyHttpUrl, Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="local", alias="DRISHTI_ENV")
    api_host: str = Field(default="0.0.0.0", alias="DRISHTI_API_HOST")
    api_port: int = Field(default=8000, alias="DRISHTI_API_PORT")
    web_origin: AnyHttpUrl = Field(default="http://localhost:3000", alias="DRISHTI_WEB_ORIGIN")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/drishti",
        alias="DATABASE_URL",
    )
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


@lru_cache
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = (
        "postgresql+psycopg://trackonomics:trackonomics_local@127.0.0.1:5432/trackonomics"
    )
    render_external_hostname: str = ""
    ingestion_enabled: bool = False
    ingestion_token: str = Field(default="", repr=False)
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver", "api"]
    max_request_bytes: int = Field(default=8192, ge=1024, le=1048576)
    musicbrainz_user_agent: str = ""
    musicbrainz_max_releases: int = 20
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value):
        for prefix in ("postgres://", "postgresql://"):
            if isinstance(value, str) and value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @model_validator(mode="after")
    def validate_ingestion(self):
        if self.render_external_hostname:
            self.allowed_hosts = [*self.allowed_hosts, self.render_external_hostname]
        if self.ingestion_enabled and (
            len(self.ingestion_token) < 32 or not self.musicbrainz_user_agent.strip()
        ):
            raise ValueError(
                "Enabled ingestion requires a token of at least 32 characters "
                "and an identifying User-Agent"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

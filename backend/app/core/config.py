from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
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
    bulk_worker_enabled: bool = True
    bulk_poll_seconds: float = Field(default=2.0, ge=0.25, le=60)
    spotify_client_id: str = Field(default="", repr=False)
    spotify_client_secret: SecretStr = Field(default=SecretStr(""), repr=False)
    spotify_market: str = Field(default="ZA", pattern=r"^[A-Z]{2}$")
    spotify_max_albums: int = Field(default=5, ge=1, le=20)
    spotify_max_tracks_per_album: int = Field(default=50, ge=1, le=200)
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
        if self.ingestion_enabled and len(self.ingestion_token) < 32:
            raise ValueError("Enabled ingestion requires a token of at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

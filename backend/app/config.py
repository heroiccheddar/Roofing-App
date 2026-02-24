"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str

    # Redis (optional — cache degrades gracefully without it)
    UPSTASH_REDIS_URL: str = ""
    UPSTASH_REDIS_TOKEN: str = ""

    # JWT Authentication
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 72

    # AWS (auto-discovered from IAM role in production, set manually for local dev)
    AWS_REGION: str = "us-east-2"
    AWS_ACCESS_KEY_ID: str | None = None  # local dev only
    AWS_SECRET_ACCESS_KEY: str | None = None  # local dev only

    # AWS SES Email
    SES_FROM_EMAIL: str = "alerts@stormleads.com"
    SES_REGION: str = "us-east-2"

    # AWS SNS SMS
    SNS_REGION: str = "us-east-1"

    # Census API (required for ingestion, optional for API-only startup)
    CENSUS_API_KEY: str = ""

    # Mapbox Geocoding (optional — for zone display names)
    MAPBOX_TOKEN: str = ""

    # OpenRouteService (for driving route optimization)
    OPENROUTESERVICE_API_KEY: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Target states for weather monitoring and base scoring
    TARGET_STATES: str = "GA"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def target_states_list(self) -> list[str]:
        """Parse target states from comma-separated string."""
        return [s.strip() for s in self.TARGET_STATES.split(",") if s.strip()]


settings = Settings()

"""Centralized environment-driven configuration for GridWise."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LLM_API_KEY: str = Field(default="", description="API key for LLM provider")
    LLM_MODEL: str = Field(default="gemini-2.5-flash", description="Model identifier")
    LLM_BASE_URL: str = Field(default="", description="Base URL for LLM provider if custom")
    LLM_TIMEOUT_SECONDS: float = Field(default=20.0, description="Timeout for LLM calls in seconds")
    PORT: int = Field(default=8000, description="Application server port")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")


settings = Settings()

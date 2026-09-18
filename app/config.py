"""Centralized environment-driven configuration for GridWise."""

import os
from typing import Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LLM_API_KEY: str = Field(default="", description="API key for LLM provider")
    LLM_MODEL: str = Field(default="gemini-3.1-flash-lite", description="Model identifier")
    LLM_BASE_URL: str = Field(default="", description="Base URL for LLM provider if custom")
    LLM_TIMEOUT_SECONDS: float = Field(default=25.0, description="Timeout for LLM calls in seconds")
    PORT: int = Field(default=8000, description="Application server port")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    @model_validator(mode="before")
    @classmethod
    def check_aliases_and_env(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Check environment alias if LLM_API_KEY not passed
            if not data.get("LLM_API_KEY"):
                data["LLM_API_KEY"] = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
            if not data.get("LLM_MODEL"):
                data["LLM_MODEL"] = os.environ.get("LLM_MODEL") or "gemini-3.1-flash-lite"
        return data


settings = Settings()

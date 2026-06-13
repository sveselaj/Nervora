"""Typed application settings, loaded once from the environment.

All services (gateway, worker, demo agent) read the same Settings object so
that policy decisions are consistent across process boundaries.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Runtime mode -----------------------------------------------------
    app_env: Literal["demo", "prod"] = "demo"

    # --- Database ---------------------------------------------------------
    database_url: str = "sqlite+pysqlite:///./smg.sqlite3"

    # --- Auth -------------------------------------------------------------
    auth_mode: Literal["dev", "entra"] = "dev"
    dev_token_signing_secret: str = "dev-only-not-for-production-change-me"
    entra_tenant_id: str = ""
    entra_audience: str = "api://secure-mcp-gateway"
    entra_issuer: str = ""
    entra_jwks_url: str = ""

    # --- Queue ------------------------------------------------------------
    queue_backend: Literal["local", "azure"] = "local"
    servicebus_connection_string: str = ""
    servicebus_queue_name: str = "tool-jobs"
    queue_max_delivery_count: int = 5

    # --- Databricks -------------------------------------------------------
    databricks_mode: Literal["mock", "real"] = "mock"
    databricks_host: str = ""
    databricks_token: str = ""
    databricks_warehouse_id: str = ""

    # --- Observability ----------------------------------------------------
    otel_enabled: bool = True
    otel_service_name: str = "mcp-gateway"
    otel_exporter_otlp_endpoint: str = ""
    otel_console_fallback: bool = True

    # --- Approvals --------------------------------------------------------
    admin_approval_token: str = Field(default="", repr=False)

    @property
    def is_demo(self) -> bool:
        return self.app_env == "demo"


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings instance."""
    return Settings()

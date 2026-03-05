"""Configuration management for nu-msgraph library.

Uses Pydantic Settings for environment variable loading with validation.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Default logger - users can replace with their own
logger = logging.getLogger("nu_msgraph")


class MSGraphConfig(BaseSettings):
    """Microsoft Graph API configuration.
    
    Configuration can be provided via:
    1. Constructor arguments
    2. Environment variables (with MS_GRAPH_ prefix)
    3. .env file
    
    Example:
        # From environment variables
        config = MSGraphConfig()
        
        # Or explicit values
        config = MSGraphConfig(
            tenant_id="...",
            client_id="...",
            client_secret="...",
            from_address="...",
        )
    """

    model_config = SettingsConfigDict(
        env_prefix="MS_GRAPH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Required OAuth2 credentials
    tenant_id: str = Field(
        default="",
        description="Azure AD Tenant ID",
    )
    client_id: str = Field(
        default="",
        description="Application (client) ID from Azure AD",
    )
    client_secret: str = Field(
        default="",
        description="Client secret for the application",
    )

    # Email settings
    from_address: str = Field(
        default="",
        description="Default sender email address (must have Mail.Send permission)",
    )

    # Webhook settings
    webhook_url: str = Field(
        default="",
        description="Public HTTPS URL for receiving webhook notifications",
    )

    # Rich Notifications encryption (optional)
    private_key: str = Field(
        default="",
        description="Base64-encoded PEM private key for Rich Notifications",
    )
    certificate: str = Field(
        default="",
        description="Base64-encoded PEM certificate for Rich Notifications",
    )
    certificate_id: str = Field(
        default="",
        description="Certificate ID for Rich Notifications",
    )

    # Feature flags
    enabled: bool = Field(
        default=True,
        description="Enable/disable MS Graph operations",
    )

    # HTTP client settings
    timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="HTTP request timeout in seconds",
    )

    @model_validator(mode="after")
    def validate_config(self) -> "MSGraphConfig":
        """Validate configuration after loading."""
        # Log warnings for missing optional config
        if not self.webhook_url:
            logger.debug("Webhook URL not configured - subscriptions will require explicit URL")
        
        if not all([self.private_key, self.certificate, self.certificate_id]):
            logger.debug("Rich Notifications certificate not configured")
        
        return self

    def is_configured(self) -> bool:
        """Check if required credentials are configured."""
        return bool(
            self.tenant_id
            and self.client_id
            and self.client_secret
            and self.from_address
        )

    def is_enabled(self) -> bool:
        """Check if MS Graph API is enabled and configured."""
        return self.enabled and self.is_configured()

    def has_crypto_config(self) -> bool:
        """Check if Rich Notifications encryption is configured."""
        return bool(
            self.private_key
            and self.certificate
            and self.certificate_id
        )

    def get_token_url(self) -> str:
        """Get the OAuth2 token endpoint URL."""
        return f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"

    def model_dump_safe(self) -> dict[str, Any]:
        """Dump config with secrets masked."""
        data = self.model_dump()
        # Mask sensitive fields
        for key in ["client_secret", "private_key"]:
            if data.get(key):
                data[key] = "***MASKED***"
        return data


def configure_logging(
    level: int = logging.INFO,
    format_string: str | None = None,
) -> None:
    """Configure logging for nu-msgraph.
    
    Args:
        level: Logging level (default: INFO).
        format_string: Custom format string (optional).
    """
    handler = logging.StreamHandler()
    handler.setLevel(level)
    
    if format_string:
        formatter = logging.Formatter(format_string)
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)

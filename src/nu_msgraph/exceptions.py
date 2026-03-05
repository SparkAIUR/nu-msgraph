"""Custom exceptions for nu-msgraph library."""

from __future__ import annotations


class MSGraphError(Exception):
    """Base exception for Microsoft Graph API errors.
    
    Attributes:
        message: Error message description.
        code: Error code from Graph API or internal code.
        status_code: HTTP status code if applicable.
    """

    def __init__(
        self,
        message: str,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.append(f"[{self.code}]")
        if self.status_code:
            parts.append(f"(HTTP {self.status_code})")
        return " ".join(parts)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"code={self.code!r}, "
            f"status_code={self.status_code!r})"
        )


class MSGraphAuthError(MSGraphError):
    """Authentication/authorization error."""

    def __init__(
        self,
        message: str = "Authentication failed",
        code: str | None = "auth_error",
        status_code: int | None = 401,
    ) -> None:
        super().__init__(message, code, status_code)


class MSGraphConfigError(MSGraphError):
    """Configuration error - missing or invalid settings."""

    def __init__(
        self,
        message: str = "Invalid configuration",
        code: str | None = "config_error",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, code, status_code)


class MSGraphNetworkError(MSGraphError):
    """Network/connectivity error."""

    def __init__(
        self,
        message: str = "Network request failed",
        code: str | None = "network_error",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, code, status_code)


class MSGraphCryptoError(MSGraphError):
    """Encryption/decryption error for Rich Notifications."""

    def __init__(
        self,
        message: str = "Cryptographic operation failed",
        code: str | None = "crypto_error",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, code, status_code)


class MSGraphSubscriptionError(MSGraphError):
    """Subscription management error."""

    def __init__(
        self,
        message: str = "Subscription operation failed",
        code: str | None = "subscription_error",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, code, status_code)


class MSGraphWebhookError(MSGraphError):
    """Webhook processing error."""

    def __init__(
        self,
        message: str = "Webhook processing failed",
        code: str | None = "webhook_error",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, code, status_code)

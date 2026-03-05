"""nu-msgraph: Microsoft Graph API client for Python.

A comprehensive Python library for Microsoft Graph API email operations
with webhook subscriptions and Rich Notifications support.

Example:
    from nu_msgraph import MSGraphClient, MSGraphConfig
    
    config = MSGraphConfig(
        tenant_id="...",
        client_id="...",
        client_secret="...",
        from_address="sender@example.com",
    )
    
    client = MSGraphClient(config)
    
    await client.send_email(
        to_address="recipient@example.com",
        subject="Hello",
        body_text="World",
    )
"""

from nu_msgraph.client import MSGraphClient
from nu_msgraph.config import MSGraphConfig, configure_logging, logger
from nu_msgraph.crypto import MSGraphCrypto
from nu_msgraph.exceptions import (
    MSGraphAuthError,
    MSGraphConfigError,
    MSGraphCryptoError,
    MSGraphError,
    MSGraphNetworkError,
    MSGraphSubscriptionError,
    MSGraphWebhookError,
)
from nu_msgraph.models import (
    ChangeNotification,
    EmailAddress,
    EmailBody,
    EmailMessage,
    EmailRecipient,
    EncryptedContent,
    NotificationPayload,
    NotificationResourceData,
    SendEmailResult,
    SubscriptionListResponse,
    SubscriptionRequest,
    SubscriptionResponse,
)
from nu_msgraph.subscription import MSGraphSubscriptionService
from nu_msgraph.webhook import (
    BaseWebhookHandler,
    LoggingWebhookHandler,
    WebhookResponse,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Client
    "MSGraphClient",
    # Config
    "MSGraphConfig",
    "configure_logging",
    "logger",
    # Crypto
    "MSGraphCrypto",
    # Subscription
    "MSGraphSubscriptionService",
    # Webhook
    "BaseWebhookHandler",
    "LoggingWebhookHandler",
    "WebhookResponse",
    # Models
    "ChangeNotification",
    "EmailAddress",
    "EmailBody",
    "EmailMessage",
    "EmailRecipient",
    "EncryptedContent",
    "NotificationPayload",
    "NotificationResourceData",
    "SendEmailResult",
    "SubscriptionListResponse",
    "SubscriptionRequest",
    "SubscriptionResponse",
    # Exceptions
    "MSGraphError",
    "MSGraphAuthError",
    "MSGraphConfigError",
    "MSGraphCryptoError",
    "MSGraphNetworkError",
    "MSGraphSubscriptionError",
    "MSGraphWebhookError",
]

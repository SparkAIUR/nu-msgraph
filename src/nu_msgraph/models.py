"""Pydantic models for Microsoft Graph API notifications and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Email Models
# ============================================================================


class EmailAddress(BaseModel):
    """Email address model."""

    address: str
    name: str | None = None


class EmailRecipient(BaseModel):
    """Email recipient wrapper."""

    model_config = ConfigDict(populate_by_name=True)

    email_address: EmailAddress = Field(alias="emailAddress")


class EmailBody(BaseModel):
    """Email body content."""

    model_config = ConfigDict(populate_by_name=True)

    content_type: str = Field(alias="contentType", default="Text")
    content: str = ""


class EmailMessage(BaseModel):
    """Email message model."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    subject: str | None = None
    body: EmailBody | None = None
    body_preview: str | None = Field(None, alias="bodyPreview")
    from_recipient: EmailRecipient | None = Field(None, alias="from")
    to_recipients: list[EmailRecipient] = Field(default_factory=list, alias="toRecipients")
    cc_recipients: list[EmailRecipient] = Field(default_factory=list, alias="ccRecipients")
    bcc_recipients: list[EmailRecipient] = Field(default_factory=list, alias="bccRecipients")
    received_datetime: datetime | None = Field(None, alias="receivedDateTime")
    sent_datetime: datetime | None = Field(None, alias="sentDateTime")
    is_read: bool = Field(False, alias="isRead")
    importance: str = "normal"
    has_attachments: bool = Field(False, alias="hasAttachments")


# ============================================================================
# Notification Models
# ============================================================================


class NotificationResourceData(BaseModel):
    """Resource data included in notifications."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(None, description="Resource ID (e.g., message ID)")
    odata_type: str | None = Field(None, alias="@odata.type")
    odata_id: str | None = Field(None, alias="@odata.id")
    odata_etag: str | None = Field(None, alias="@odata.etag")


class EncryptedContent(BaseModel):
    """Encrypted content from Rich Notifications."""

    model_config = ConfigDict(populate_by_name=True)

    data: str = Field(..., description="Base64-encoded encrypted data")
    data_key: str = Field(..., alias="dataKey", description="Base64-encoded encrypted symmetric key")
    data_signature: str | None = Field(None, alias="dataSignature", description="HMAC-SHA256 signature")
    encryption_certificate_id: str | None = Field(
        None, alias="encryptionCertificateId", description="Certificate ID used for encryption"
    )
    encryption_certificate_thumbprint: str | None = Field(
        None, alias="encryptionCertificateThumbprint"
    )


class ChangeNotification(BaseModel):
    """Individual change notification from Microsoft Graph.
    
    Represents a single notification about a resource change.
    """

    model_config = ConfigDict(populate_by_name=True)

    subscription_id: str | None = Field(None, alias="subscriptionId")
    subscription_expiration_datetime: str | None = Field(
        None, alias="subscriptionExpirationDateTime"
    )
    change_type: str | None = Field(None, alias="changeType")
    resource: str | None = None
    resource_data: NotificationResourceData | None = Field(None, alias="resourceData")
    client_state: str | None = Field(None, alias="clientState")
    tenant_id: str | None = Field(None, alias="tenantId")

    # Rich notification fields (encrypted)
    encrypted_content: EncryptedContent | None = Field(None, alias="encryptedContent")

    # Populated after decryption (not from Graph API)
    decrypted_content: dict[str, Any] | None = Field(None, exclude=True)

    @property
    def message_id(self) -> str | None:
        """Extract message ID from resource data."""
        if self.resource_data:
            return self.resource_data.id
        return None

    @property
    def is_rich_notification(self) -> bool:
        """Check if this is a Rich Notification with encrypted content."""
        return self.encrypted_content is not None


class NotificationPayload(BaseModel):
    """Webhook notification payload from Microsoft Graph.
    
    Contains a list of change notifications.
    """

    value: list[ChangeNotification] = Field(default_factory=list)


# ============================================================================
# Subscription Models
# ============================================================================


class SubscriptionRequest(BaseModel):
    """Request model for creating a subscription."""

    user_email: str | None = Field(None, description="Email address to monitor")
    webhook_url: str | None = Field(None, description="Override default webhook URL")
    expiration_hours: int = Field(
        72, ge=1, le=72, description="Subscription validity in hours (max 72)"
    )
    change_types: list[str] = Field(
        default_factory=lambda: ["created"],
        description="Change types to monitor: created, updated, deleted",
    )
    include_resource_data: bool = Field(
        False, description="Enable Rich Notifications with encrypted content"
    )
    client_state: str | None = Field(
        None, description="Secret for validating notifications"
    )


class SubscriptionResponse(BaseModel):
    """Response model for subscription operations."""

    subscription_id: str
    user_email: str
    notification_url: str
    expiration_datetime: str
    change_type: str | None = None
    resource: str | None = None
    client_state: str | None = None
    include_resource_data: bool = False


class SubscriptionListResponse(BaseModel):
    """List of subscriptions response."""

    subscriptions: list[dict[str, Any]]
    count: int


# ============================================================================
# API Response Models
# ============================================================================


class SendEmailResult(BaseModel):
    """Result of sending an email."""

    status: str = "sent"
    request_id: str
    to: str
    subject: str


class GraphErrorDetail(BaseModel):
    """Error detail from Graph API."""

    model_config = ConfigDict(populate_by_name=True)

    code: str | None = None
    message: str | None = None
    inner_error: dict[str, Any] | None = Field(None, alias="innerError")


class GraphErrorResponse(BaseModel):
    """Error response from Graph API."""

    error: GraphErrorDetail | None = None

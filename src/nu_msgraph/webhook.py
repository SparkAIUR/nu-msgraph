"""Base webhook handler for Microsoft Graph notifications.

This module provides a framework-agnostic base class for handling
webhook notifications from Microsoft Graph.

Implement the abstract methods in your subclass to handle specific
notification types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from nu_msgraph.config import MSGraphConfig, logger
from nu_msgraph.crypto import MSGraphCrypto
from nu_msgraph.exceptions import MSGraphCryptoError, MSGraphWebhookError
from nu_msgraph.models import ChangeNotification, NotificationPayload


@runtime_checkable
class WebRequest(Protocol):
    """Protocol for web framework request objects.
    
    Supports FastAPI, Flask, Django, etc. by duck typing.
    """

    @property
    def query_params(self) -> dict[str, str]:
        """Query parameters dictionary."""
        ...

    async def json(self) -> dict[str, Any]:
        """Parse request body as JSON."""
        ...


class WebhookResponse:
    """Framework-agnostic webhook response.
    
    Can be converted to framework-specific response objects.
    """

    def __init__(
        self,
        content: str = "",
        status_code: int = 200,
        media_type: str = "text/plain",
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.media_type = media_type

    @classmethod
    def validation_response(cls, token: str) -> "WebhookResponse":
        """Create validation response for subscription setup."""
        return cls(content=token, status_code=200, media_type="text/plain")

    @classmethod
    def accepted(cls) -> "WebhookResponse":
        """Create 202 Accepted response for notifications."""
        return cls(content="", status_code=202, media_type="text/plain")

    @classmethod
    def error(cls, message: str, status_code: int = 400) -> "WebhookResponse":
        """Create error response."""
        return cls(content=message, status_code=status_code, media_type="text/plain")


class BaseWebhookHandler(ABC):
    """Base class for handling Microsoft Graph webhook notifications.
    
    Subclass this to implement your notification handling logic.
    
    Example:
        class MyWebhookHandler(BaseWebhookHandler):
            async def on_email_created(self, notification: ChangeNotification) -> None:
                print(f"New email: {notification.message_id}")
                
            async def on_email_updated(self, notification: ChangeNotification) -> None:
                print(f"Updated email: {notification.message_id}")
                
            async def on_email_deleted(self, notification: ChangeNotification) -> None:
                print(f"Deleted email: {notification.message_id}")
        
        # FastAPI integration
        from fastapi import FastAPI, Request, Response
        
        app = FastAPI()
        handler = MyWebhookHandler(config=config, crypto=crypto)
        
        @app.post("/webhook/notifications")
        async def webhook(request: Request) -> Response:
            result = await handler.process_request(request)
            return Response(
                content=result.content,
                status_code=result.status_code,
                media_type=result.media_type,
            )
    """

    def __init__(
        self,
        config: MSGraphConfig | None = None,
        crypto: MSGraphCrypto | None = None,
        validate_client_state: bool = False,
        expected_client_states: set[str] | None = None,
    ) -> None:
        """Initialize webhook handler.
        
        Args:
            config: Optional configuration.
            crypto: Optional crypto service for Rich Notifications decryption.
            validate_client_state: Whether to validate client state in notifications.
            expected_client_states: Set of valid client states to accept.
        """
        self.config = config or MSGraphConfig()
        self.crypto = crypto
        self.validate_client_state = validate_client_state
        self.expected_client_states = expected_client_states or set()

    async def process_request(
        self,
        request: WebRequest | dict[str, Any],
        query_params: dict[str, str] | None = None,
    ) -> WebhookResponse:
        """Process incoming webhook request.
        
        Handles both validation requests and notification payloads.
        
        Args:
            request: Web request object or raw body dict.
            query_params: Query parameters (if request is a dict).
            
        Returns:
            WebhookResponse to send back to Microsoft.
        """
        # Handle validation token
        if isinstance(request, dict):
            # Raw body provided
            params = query_params or {}
            body = request
        else:
            # Request object
            params = dict(request.query_params) if hasattr(request, "query_params") else {}
            validation_token = params.get("validationToken")
            if validation_token:
                logger.info("MS Graph webhook validation requested")
                return WebhookResponse.validation_response(validation_token)
            
            try:
                body = await request.json()
            except Exception as e:
                logger.error(f"Failed to parse webhook body: {e}")
                return WebhookResponse.error("Invalid JSON payload", 400)

        # Check for validation token in params
        validation_token = params.get("validationToken")
        if validation_token:
            logger.info("MS Graph webhook validation requested")
            return WebhookResponse.validation_response(validation_token)

        # Process notifications
        try:
            await self.process_notifications(body)
        except Exception as e:
            logger.error(f"Error processing notifications: {e}")
            # Still return 202 to prevent retries for app errors
            # Microsoft will retry on 5xx errors

        return WebhookResponse.accepted()

    async def process_notifications(self, body: dict[str, Any]) -> int:
        """Process notification payload.
        
        Args:
            body: Raw notification payload.
            
        Returns:
            Number of notifications processed.
        """
        notifications = body.get("value", [])
        processed_count = 0

        for notification_data in notifications:
            try:
                notification = ChangeNotification.model_validate(notification_data)
                
                # Validate client state if configured
                if self.validate_client_state and notification.client_state:
                    if notification.client_state not in self.expected_client_states:
                        logger.warning(
                            f"Invalid client state: {notification.client_state}"
                        )
                        continue

                # Handle Rich Notifications (decrypt if possible)
                if notification.encrypted_content and self.crypto:
                    try:
                        if self.crypto.is_configured():
                            notification.decrypted_content = self.crypto.decrypt_notification(
                                notification.encrypted_content.model_dump(by_alias=True)
                            )
                            logger.debug("Successfully decrypted Rich Notification content")
                    except MSGraphCryptoError as e:
                        logger.error(f"Failed to decrypt Rich Notification: {e}")

                # Log notification receipt
                logger.info(
                    f"MS Graph notification: "
                    f"subscription={notification.subscription_id}, "
                    f"change_type={notification.change_type}, "
                    f"message_id={notification.message_id}"
                )

                # Dispatch to appropriate handler
                await self._dispatch_notification(notification)
                processed_count += 1

            except Exception as e:
                logger.error(f"Error processing notification: {e}")
                # Continue processing other notifications

        logger.info(f"Processed {processed_count}/{len(notifications)} notifications")
        return processed_count

    async def _dispatch_notification(self, notification: ChangeNotification) -> None:
        """Dispatch notification to appropriate handler method.
        
        Args:
            notification: Parsed notification object.
        """
        change_type = notification.change_type

        if change_type == "created":
            await self.on_email_created(notification)
        elif change_type == "updated":
            await self.on_email_updated(notification)
        elif change_type == "deleted":
            await self.on_email_deleted(notification)
        else:
            logger.warning(f"Unknown change type: {change_type}")
            await self.on_unknown_change(notification)

    @abstractmethod
    async def on_email_created(self, notification: ChangeNotification) -> None:
        """Handle notification of a new email arrival.
        
        Override this method to implement your email processing logic.
        
        Args:
            notification: The notification with email data.
                - notification.message_id: The email message ID
                - notification.decrypted_content: Full email data (if Rich Notifications)
        """
        pass

    @abstractmethod
    async def on_email_updated(self, notification: ChangeNotification) -> None:
        """Handle notification of an email update.
        
        Override this method to handle email updates (read status, etc.).
        
        Args:
            notification: The notification with email data.
        """
        pass

    @abstractmethod
    async def on_email_deleted(self, notification: ChangeNotification) -> None:
        """Handle notification of an email deletion.
        
        Override this method to handle email deletions.
        
        Args:
            notification: The notification with message ID.
        """
        pass

    async def on_unknown_change(self, notification: ChangeNotification) -> None:
        """Handle unknown change types.
        
        Override this method to handle unexpected change types.
        Default implementation logs a warning.
        
        Args:
            notification: The notification.
        """
        logger.warning(f"Unhandled change type: {notification.change_type}")


class LoggingWebhookHandler(BaseWebhookHandler):
    """Simple webhook handler that logs all notifications.
    
    Useful for debugging and testing.
    """

    async def on_email_created(self, notification: ChangeNotification) -> None:
        """Log new email notification."""
        logger.info(f"[CREATED] New email: message_id={notification.message_id}")
        if notification.decrypted_content:
            subject = notification.decrypted_content.get("subject", "(no subject)")
            sender = (
                notification.decrypted_content.get("from", {})
                .get("emailAddress", {})
                .get("address", "unknown")
            )
            logger.info(f"  Subject: {subject}, From: {sender}")

    async def on_email_updated(self, notification: ChangeNotification) -> None:
        """Log email update notification."""
        logger.info(f"[UPDATED] Email updated: message_id={notification.message_id}")

    async def on_email_deleted(self, notification: ChangeNotification) -> None:
        """Log email deletion notification."""
        logger.info(f"[DELETED] Email deleted: message_id={notification.message_id}")

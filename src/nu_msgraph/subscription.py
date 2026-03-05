"""Microsoft Graph API subscription management for email notifications.

This module handles:
- Creating change notification subscriptions
- Renewing subscriptions before expiration (max 72 hours)
- Managing subscription lifecycle

References:
- Rich Notifications: https://learn.microsoft.com/en-us/graph/change-notifications-with-resource-data
- Webhook Delivery: https://learn.microsoft.com/en-us/graph/change-notifications-delivery-webhooks
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Any
from uuid import uuid4

import httpx

from nu_msgraph.client import MSGraphClient
from nu_msgraph.config import MSGraphConfig, logger
from nu_msgraph.crypto import MSGraphCrypto
from nu_msgraph.exceptions import (
    MSGraphConfigError,
    MSGraphError,
    MSGraphNetworkError,
    MSGraphSubscriptionError,
)


class MSGraphSubscriptionService:
    """Manage Graph API change notification subscriptions.
    
    Subscriptions allow receiving notifications when emails arrive.
    Maximum subscription validity is 72 hours (3 days).
    
    Example:
        config = MSGraphConfig(...)
        client = MSGraphClient(config)
        subscription_service = MSGraphSubscriptionService(client, config)
        
        # Create subscription for new emails
        result = await subscription_service.create_subscription(
            change_types=["created"],
            expiration_hours=72,
        )
    """

    # Maximum subscription validity in hours (Graph API limit)
    MAX_SUBSCRIPTION_HOURS = 72

    # Renew subscriptions this many hours before expiration
    RENEWAL_BUFFER_HOURS = 24

    def __init__(
        self,
        client: MSGraphClient,
        config: MSGraphConfig | None = None,
        crypto: MSGraphCrypto | None = None,
    ) -> None:
        """Initialize subscription service.
        
        Args:
            client: MSGraphClient instance for API calls.
            config: Optional config (uses client's config if not provided).
            crypto: Optional crypto service for Rich Notifications.
        """
        self.client = client
        self.config = config or client.config
        self.crypto = crypto

    async def create_subscription(
        self,
        *,
        user_email: str | None = None,
        webhook_url: str | None = None,
        expiration_hours: int = 72,
        change_types: list[str] | None = None,
        include_resource_data: bool = False,
        client_state: str | None = None,
    ) -> dict[str, Any]:
        """Create a subscription for email change notifications.
        
        Args:
            user_email: Email address to monitor. Defaults to configured from_address.
            webhook_url: Public HTTPS URL for notifications. Defaults to configured webhook_url.
            expiration_hours: Subscription validity in hours (max 72).
            change_types: List of change types to monitor ("created", "updated", "deleted").
            include_resource_data: Whether to include full email data in notifications (Rich Notifications).
            client_state: Optional secret for validating notifications.
            
        Returns:
            Subscription details including subscription ID.
            
        Raises:
            MSGraphSubscriptionError: If subscription creation fails.
            MSGraphConfigError: If not configured.
            
        Note:
            Rich Notifications (include_resource_data=True) require:
            - Certificate encryption setup via MSGraphCrypto
            - encryptionCertificate and encryptionCertificateId in request
        """
        if not self.client.is_configured:
            raise MSGraphConfigError("MS Graph API is not configured")

        email = user_email or self.config.from_address
        if not email:
            raise MSGraphConfigError("No email address provided")

        webhook = webhook_url or self.config.webhook_url
        if not webhook:
            raise MSGraphConfigError("No webhook URL configured")

        # Calculate expiration (max 72 hours)
        hours = min(expiration_hours, self.MAX_SUBSCRIPTION_HOURS)
        expiration = datetime.now(UTC) + timedelta(hours=hours)

        # Default to monitoring new emails only
        if change_types is None:
            change_types = ["created"]

        # Generate client state for validation if not provided
        if client_state is None:
            client_state = uuid4().hex

        # Build subscription payload
        subscription: dict[str, Any] = {
            "changeType": ",".join(change_types),
            "notificationUrl": webhook,
            "resource": f"/users/{email}/messages",
            "expirationDateTime": expiration.isoformat().replace("+00:00", "Z"),
            "clientState": client_state,
        }

        # Rich Notifications require encryption setup
        if include_resource_data:
            if self.crypto and self.crypto.is_configured():
                subscription["includeResourceData"] = True
                subscription["encryptionCertificate"] = self.crypto.get_certificate_base64()
                subscription["encryptionCertificateId"] = self.crypto.get_certificate_id()
                logger.info("Rich Notifications enabled with certificate encryption")
            else:
                logger.warning(
                    "Rich Notifications requested but certificate not configured - "
                    "using basic notifications. Configure MSGraphCrypto with certificate."
                )

        # Get access token
        token = await self.client._get_access_token()
        headers = self.client._build_headers(token)

        url = f"{self.client.GRAPH_API_BASE}/subscriptions"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as http_client:
                response = await http_client.post(url, json=subscription, headers=headers)

                if response.status_code in (200, 201):
                    data = response.json()
                    logger.info(
                        f"MS Graph subscription created: {data.get('id')} "
                        f"for {email}, expires {data.get('expirationDateTime')}"
                    )
                    return {
                        "subscription_id": data.get("id"),
                        "resource": data.get("resource"),
                        "change_type": data.get("changeType"),
                        "notification_url": data.get("notificationUrl"),
                        "expiration_datetime": data.get("expirationDateTime"),
                        "client_state": client_state,
                        "user_email": email,
                        "include_resource_data": include_resource_data and self.crypto is not None,
                    }

                # Handle errors
                error_data = response.json() if response.content else {}
                error_info = error_data.get("error", {})
                error_msg = error_info.get(
                    "message", f"Subscription failed with status {response.status_code}"
                )
                error_code = error_info.get("code", "subscription_error")

                logger.error(f"MS Graph subscription failed: {error_code} - {error_msg}")
                raise MSGraphSubscriptionError(
                    error_msg, code=error_code, status_code=response.status_code
                )

        except httpx.RequestError as e:
            logger.error(f"MS Graph subscription request failed: {e}")
            raise MSGraphNetworkError(f"Subscription request failed: {e}") from e

    async def renew_subscription(
        self,
        subscription_id: str,
        expiration_hours: int = 72,
    ) -> dict[str, Any]:
        """Renew an existing subscription before it expires.
        
        Args:
            subscription_id: The subscription ID to renew.
            expiration_hours: New validity period in hours (max 72).
            
        Returns:
            Updated subscription details.
            
        Raises:
            MSGraphSubscriptionError: If renewal fails.
        """
        if not self.client.is_configured:
            raise MSGraphConfigError("MS Graph API is not configured")

        # Calculate new expiration
        hours = min(expiration_hours, self.MAX_SUBSCRIPTION_HOURS)
        expiration = datetime.now(UTC) + timedelta(hours=hours)

        payload = {
            "expirationDateTime": expiration.isoformat().replace("+00:00", "Z"),
        }

        token = await self.client._get_access_token()
        headers = self.client._build_headers(token)

        url = f"{self.client.GRAPH_API_BASE}/subscriptions/{subscription_id}"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as http_client:
                response = await http_client.patch(url, json=payload, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        f"MS Graph subscription renewed: {subscription_id}, "
                        f"new expiration: {data.get('expirationDateTime')}"
                    )
                    return {
                        "subscription_id": data.get("id"),
                        "expiration_datetime": data.get("expirationDateTime"),
                        "renewed": True,
                    }

                if response.status_code == 404:
                    raise MSGraphSubscriptionError(
                        f"Subscription not found: {subscription_id}",
                        code="subscription_not_found",
                        status_code=404,
                    )

                error_data = response.json() if response.content else {}
                error_info = error_data.get("error", {})
                error_msg = error_info.get("message", "Renewal failed")
                error_code = error_info.get("code", "renewal_error")

                raise MSGraphSubscriptionError(
                    error_msg, code=error_code, status_code=response.status_code
                )

        except httpx.RequestError as e:
            raise MSGraphNetworkError(f"Renewal request failed: {e}") from e

    async def delete_subscription(self, subscription_id: str) -> bool:
        """Delete an existing subscription.
        
        Args:
            subscription_id: The subscription ID to delete.
            
        Returns:
            True if deleted successfully.
            
        Raises:
            MSGraphSubscriptionError: If deletion fails.
        """
        if not self.client.is_configured:
            raise MSGraphConfigError("MS Graph API is not configured")

        token = await self.client._get_access_token()
        headers = self.client._build_headers(token)

        url = f"{self.client.GRAPH_API_BASE}/subscriptions/{subscription_id}"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as http_client:
                response = await http_client.delete(url, headers=headers)

                if response.status_code == 204:
                    logger.info(f"MS Graph subscription deleted: {subscription_id}")
                    return True

                if response.status_code == 404:
                    logger.warning(f"MS Graph subscription not found: {subscription_id}")
                    return True  # Already deleted

                error_data = response.json() if response.content else {}
                error_info = error_data.get("error", {})
                error_msg = error_info.get("message", "Deletion failed")
                error_code = error_info.get("code", "deletion_error")

                raise MSGraphSubscriptionError(
                    error_msg, code=error_code, status_code=response.status_code
                )

        except httpx.RequestError as e:
            raise MSGraphNetworkError(f"Deletion request failed: {e}") from e

    async def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Get details of an existing subscription.
        
        Args:
            subscription_id: The subscription ID to retrieve.
            
        Returns:
            Subscription details.
            
        Raises:
            MSGraphSubscriptionError: If retrieval fails.
        """
        if not self.client.is_configured:
            raise MSGraphConfigError("MS Graph API is not configured")

        token = await self.client._get_access_token()
        headers = self.client._build_headers(token)

        url = f"{self.client.GRAPH_API_BASE}/subscriptions/{subscription_id}"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as http_client:
                response = await http_client.get(url, headers=headers)

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 404:
                    raise MSGraphSubscriptionError(
                        f"Subscription not found: {subscription_id}",
                        code="subscription_not_found",
                        status_code=404,
                    )

                error_data = response.json() if response.content else {}
                error_info = error_data.get("error", {})
                error_msg = error_info.get("message", "Get subscription failed")
                error_code = error_info.get("code", "get_error")

                raise MSGraphSubscriptionError(
                    error_msg, code=error_code, status_code=response.status_code
                )

        except httpx.RequestError as e:
            raise MSGraphNetworkError(f"Get subscription request failed: {e}") from e

    async def list_subscriptions(self) -> list[dict[str, Any]]:
        """List all active subscriptions.
        
        Returns:
            List of subscription details.
            
        Raises:
            MSGraphSubscriptionError: If listing fails.
        """
        if not self.client.is_configured:
            raise MSGraphConfigError("MS Graph API is not configured")

        token = await self.client._get_access_token()
        headers = self.client._build_headers(token)

        url = f"{self.client.GRAPH_API_BASE}/subscriptions"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as http_client:
                response = await http_client.get(url, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    return data.get("value", [])

                error_data = response.json() if response.content else {}
                error_info = error_data.get("error", {})
                error_msg = error_info.get("message", "List subscriptions failed")
                error_code = error_info.get("code", "list_error")

                raise MSGraphSubscriptionError(
                    error_msg, code=error_code, status_code=response.status_code
                )

        except httpx.RequestError as e:
            raise MSGraphNetworkError(f"List subscriptions request failed: {e}") from e

    def needs_renewal(self, expiration_datetime: str | datetime) -> bool:
        """Check if a subscription needs renewal.
        
        Args:
            expiration_datetime: Subscription expiration time (ISO string or datetime).
            
        Returns:
            True if subscription should be renewed.
        """
        if isinstance(expiration_datetime, str):
            # Parse ISO format
            expiration_datetime = expiration_datetime.replace("Z", "+00:00")
            expiration = datetime.fromisoformat(expiration_datetime)
        else:
            expiration = expiration_datetime

        # Ensure timezone aware
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=UTC)

        renewal_threshold = datetime.now(UTC) + timedelta(hours=self.RENEWAL_BUFFER_HOURS)
        return expiration <= renewal_threshold

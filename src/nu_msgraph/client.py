"""Microsoft Graph API client for email operations.

This module provides the main client for Microsoft Graph API:
- OAuth2 client credentials authentication
- Token caching with auto-refresh
- Send, list, and retrieve emails
- Rich error handling
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import httpx

from nu_msgraph.config import MSGraphConfig, logger
from nu_msgraph.exceptions import (
    MSGraphAuthError,
    MSGraphConfigError,
    MSGraphError,
    MSGraphNetworkError,
)


class MSGraphClient:
    """Client for Microsoft Graph API email operations.
    
    Uses OAuth2 client credentials flow for authentication.
    Tokens are cached at class level and auto-refreshed before expiration.
    
    Example:
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

    # Graph API base URL
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

    # Class-level token cache (shared across instances with same tenant)
    _token_cache: dict[str, tuple[str, float]] = {}  # tenant_id -> (token, expires_at)
    _token_lock: asyncio.Lock | None = None
    _token_lock_init_guard = threading.Lock()

    def __init__(self, config: MSGraphConfig | None = None) -> None:
        """Initialize the MS Graph client.
        
        Args:
            config: Configuration object. If None, loads from environment.
        """
        self.config = config or MSGraphConfig()
        self._http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "MSGraphClient":
        """Enter async context manager."""
        self._http_client = httpx.AsyncClient()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def is_configured(self) -> bool:
        """Check if all required credentials are configured."""
        return self.config.is_configured()

    @property
    def is_enabled(self) -> bool:
        """Check if MS Graph API is enabled and configured."""
        return self.config.is_enabled()

    def _get_cache_key(self) -> str:
        """Get cache key for token storage."""
        return f"{self.config.tenant_id}:{self.config.client_id}"

    @staticmethod
    def _safe_error_json(response: httpx.Response) -> dict[str, Any]:
        """Safely parse JSON from error response."""
        if not response.content:
            return {}
        try:
            parsed = response.json()
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}

    def _parse_json_object(self, response: httpx.Response) -> dict[str, Any]:
        """Parse successful JSON response and enforce object payload."""
        try:
            payload = response.json()
        except ValueError as e:
            raise MSGraphError(
                "Invalid JSON response from Microsoft Graph",
                code="invalid_response",
                status_code=response.status_code,
            ) from e
        if not isinstance(payload, dict):
            raise MSGraphError(
                "Unexpected response payload shape",
                code="invalid_response",
                status_code=response.status_code,
            )
        return payload

    @staticmethod
    def _mask_email(email: str) -> str:
        """Mask email address for logging (privacy)."""
        if "@" not in email:
            return email[:2] + "***"
        local, domain = email.split("@", 1)
        return f"{local[:2]}***@{domain}"

    async def _get_access_token(self) -> str:
        """Get OAuth2 access token using client credentials flow.
        
        Tokens are cached and automatically refreshed 60 seconds before expiration.
        Uses asyncio.Lock to prevent race conditions with concurrent requests.
        
        Returns:
            Valid access token for Graph API calls.
            
        Raises:
            MSGraphAuthError: If authentication fails.
            MSGraphConfigError: If not configured.
        """
        if not self.is_configured:
            raise MSGraphConfigError("MS Graph API is not configured")

        cache_key = self._get_cache_key()

        # Quick check without lock first
        if cache_key in MSGraphClient._token_cache:
            token, expires_at = MSGraphClient._token_cache[cache_key]
            if time.time() < expires_at:
                return token

        # Lazy init lock to avoid event loop issues
        if MSGraphClient._token_lock is None:
            with MSGraphClient._token_lock_init_guard:
                if MSGraphClient._token_lock is None:
                    MSGraphClient._token_lock = asyncio.Lock()

        async with MSGraphClient._token_lock:
            # Double-check after acquiring lock
            if cache_key in MSGraphClient._token_cache:
                token, expires_at = MSGraphClient._token_cache[cache_key]
                if time.time() < expires_at:
                    return token

            return await self._fetch_new_token()

    async def _fetch_new_token(self) -> str:
        """Fetch a new access token from Azure AD. Called under lock."""
        token_url = self.config.get_token_url()

        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(token_url, data=data)

                if response.status_code != 200:
                    error_data = self._safe_error_json(response)
                    error_msg = error_data.get("error_description", "Authentication failed")
                    error_code = error_data.get("error", "auth_error")
                    logger.error(f"MS Graph authentication failed: {error_msg}")
                    raise MSGraphAuthError(error_msg, code=error_code, status_code=response.status_code)

                try:
                    token_data = response.json()
                except ValueError as e:
                    logger.error("MS Graph token response was not valid JSON")
                    raise MSGraphAuthError(
                        "Authentication failed: invalid token response format",
                        code="invalid_token_response",
                        status_code=response.status_code,
                    ) from e

                if not isinstance(token_data, dict):
                    logger.error("MS Graph token response JSON was not an object")
                    raise MSGraphAuthError(
                        "Authentication failed: invalid token response payload",
                        code="invalid_token_response",
                        status_code=response.status_code,
                    )

                access_token = token_data.get("access_token")
                if not access_token:
                    logger.error("MS Graph token response missing access_token")
                    raise MSGraphAuthError(
                        "Authentication failed: missing access token",
                        code="invalid_token_response",
                        status_code=response.status_code,
                    )

                # Validate and parse expires_in
                expires_raw = token_data.get("expires_in", 3600)
                try:
                    expires_in = int(expires_raw)
                except (TypeError, ValueError):
                    expires_in = 3600

                # Cache token with 60 second buffer before expiration
                cache_key = self._get_cache_key()
                MSGraphClient._token_cache[cache_key] = (
                    access_token,
                    time.time() + max(expires_in - 60, 0),
                )

                logger.debug("MS Graph access token acquired successfully")
                return access_token

        except httpx.RequestError as e:
            logger.error(f"MS Graph authentication request failed: {e}")
            raise MSGraphNetworkError(f"Authentication request failed: {e}") from e

    def _build_headers(self, token: str) -> dict[str, str]:
        """Build HTTP headers for Graph API requests."""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def send_email(
        self,
        *,
        to_address: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        from_address: str | None = None,
        cc_addresses: list[str] | None = None,
        bcc_addresses: list[str] | None = None,
        reply_to_address: str | None = None,
        importance: str = "normal",
        save_to_sent_items: bool = True,
    ) -> dict[str, Any]:
        """Send an email via Microsoft Graph API.
        
        Args:
            to_address: Recipient email address.
            subject: Email subject line.
            body_text: Plain text body content.
            body_html: Optional HTML body content (overrides body_text if provided).
            from_address: Sender address (defaults to configured from_address).
            cc_addresses: Optional list of CC recipients.
            bcc_addresses: Optional list of BCC recipients.
            reply_to_address: Optional reply-to address.
            importance: Email importance: "low", "normal", or "high".
            save_to_sent_items: Whether to save email to Sent Items folder.
            
        Returns:
            Dictionary with send result including request_id.
            
        Raises:
            MSGraphError: If sending fails.
            MSGraphConfigError: If not configured.
        """
        if not self.is_enabled:
            raise MSGraphConfigError("MS Graph API is not enabled or not configured")

        sender = from_address or self.config.from_address
        if not sender:
            raise MSGraphConfigError("No sender email address configured")

        # Build message payload
        message: dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": "HTML" if body_html else "Text",
                "content": body_html or body_text,
            },
            "toRecipients": [{"emailAddress": {"address": to_address}}],
            "importance": importance,
        }

        # Add optional recipients
        if cc_addresses:
            message["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc_addresses
            ]

        if bcc_addresses:
            message["bccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in bcc_addresses
            ]

        if reply_to_address:
            message["replyTo"] = [{"emailAddress": {"address": reply_to_address}}]

        # Build request payload
        payload = {
            "message": message,
            "saveToSentItems": save_to_sent_items,
        }

        # Get access token
        token = await self._get_access_token()
        headers = self._build_headers(token)

        # Send the email
        url = f"{self.GRAPH_API_BASE}/users/{sender}/sendMail"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)

                # 202 Accepted is the expected response for sendMail
                if response.status_code in (200, 202):
                    request_id = response.headers.get("request-id", "")
                    logger.info(
                        f"MS Graph email sent, request_id={request_id}, "
                        f"recipient={self._mask_email(to_address)}"
                    )
                    return {
                        "status": "sent",
                        "request_id": request_id,
                        "to": to_address,
                        "subject": subject,
                    }

                # Handle errors
                error_data = self._safe_error_json(response)
                error_info = error_data.get("error", {})
                error_msg = error_info.get("message", f"Send failed with status {response.status_code}")
                error_code = error_info.get("code", "send_error")

                logger.error(f"MS Graph send failed: {error_code} - {error_msg}")
                raise MSGraphError(error_msg, code=error_code, status_code=response.status_code)

        except httpx.RequestError as e:
            logger.error(f"MS Graph send request failed: {e}")
            raise MSGraphNetworkError(f"Send request failed: {e}") from e

    async def get_user_info(self, user_email: str | None = None) -> dict[str, Any]:
        """Get user information from Graph API.
        
        Useful for verifying the configured mailbox exists and is accessible.
        
        Args:
            user_email: Email address to look up. Defaults to configured from_address.
            
        Returns:
            User information dictionary.
            
        Raises:
            MSGraphError: If user lookup fails.
        """
        if not self.is_configured:
            raise MSGraphConfigError("MS Graph API is not configured")

        email = user_email or self.config.from_address
        if not email:
            raise MSGraphConfigError("No email address provided")

        token = await self._get_access_token()
        headers = self._build_headers(token)

        url = f"{self.GRAPH_API_BASE}/users/{email}"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    return self._parse_json_object(response)

                if response.status_code == 404:
                    raise MSGraphError(
                        f"User not found: {email}",
                        code="user_not_found",
                        status_code=404,
                    )

                error_data = self._safe_error_json(response)
                error_info = error_data.get("error", {})
                error_msg = error_info.get("message", "User lookup failed")
                error_code = error_info.get("code", "lookup_error")

                raise MSGraphError(error_msg, code=error_code, status_code=response.status_code)

        except httpx.RequestError as e:
            raise MSGraphNetworkError(f"User lookup request failed: {e}") from e

    async def list_messages(
        self,
        user_email: str | None = None,
        folder: str = "inbox",
        top: int = 10,
        select: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List messages from a user's mailbox.
        
        Args:
            user_email: Email address of the mailbox. Defaults to configured from_address.
            folder: Mail folder to list (inbox, sentItems, drafts, etc.).
            top: Maximum number of messages to return.
            select: List of fields to select (for efficiency).
            
        Returns:
            List of message dictionaries.
            
        Raises:
            MSGraphError: If listing fails.
        """
        if not self.is_configured:
            raise MSGraphConfigError("MS Graph API is not configured")

        email = user_email or self.config.from_address
        if not email:
            raise MSGraphConfigError("No email address provided")

        token = await self._get_access_token()
        headers = self._build_headers(token)

        # Build URL with query parameters
        url = f"{self.GRAPH_API_BASE}/users/{email}/mailFolders/{folder}/messages"
        params: dict[str, Any] = {"$top": top}

        if select:
            params["$select"] = ",".join(select)
        else:
            # Default selection for efficiency
            params["$select"] = "id,subject,from,receivedDateTime,isRead"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.get(url, headers=headers, params=params)

                if response.status_code == 200:
                    data = self._parse_json_object(response)
                    return data.get("value", [])

                error_data = self._safe_error_json(response)
                error_info = error_data.get("error", {})
                error_msg = error_info.get("message", "List messages failed")
                error_code = error_info.get("code", "list_error")

                raise MSGraphError(error_msg, code=error_code, status_code=response.status_code)

        except httpx.RequestError as e:
            raise MSGraphNetworkError(f"List messages request failed: {e}") from e

    async def get_message(
        self,
        message_id: str,
        user_email: str | None = None,
        include_body: bool = True,
    ) -> dict[str, Any]:
        """Get a specific message by ID.
        
        Args:
            message_id: The message ID.
            user_email: Email address of the mailbox. Defaults to configured from_address.
            include_body: Whether to include the message body.
            
        Returns:
            Message dictionary.
            
        Raises:
            MSGraphError: If retrieval fails.
        """
        if not self.is_configured:
            raise MSGraphConfigError("MS Graph API is not configured")

        email = user_email or self.config.from_address
        if not email:
            raise MSGraphConfigError("No email address provided")

        token = await self._get_access_token()
        headers = self._build_headers(token)

        url = f"{self.GRAPH_API_BASE}/users/{email}/messages/{message_id}"
        params: dict[str, Any] = {}

        if not include_body:
            params["$select"] = "id,subject,from,toRecipients,receivedDateTime,isRead"

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.get(url, headers=headers, params=params)

                if response.status_code == 200:
                    return self._parse_json_object(response)

                if response.status_code == 404:
                    raise MSGraphError(
                        f"Message not found: {message_id}",
                        code="message_not_found",
                        status_code=404,
                    )

                error_data = self._safe_error_json(response)
                error_info = error_data.get("error", {})
                error_msg = error_info.get("message", "Get message failed")
                error_code = error_info.get("code", "get_error")

                raise MSGraphError(error_msg, code=error_code, status_code=response.status_code)

        except httpx.RequestError as e:
            raise MSGraphNetworkError(f"Get message request failed: {e}") from e

    @classmethod
    def clear_token_cache(cls, tenant_id: str | None = None) -> None:
        """Clear cached access tokens.
        
        Args:
            tenant_id: Clear only for specific tenant. If None, clears all.
        """
        if tenant_id:
            keys_to_remove = [k for k in cls._token_cache if k.startswith(tenant_id)]
            for key in keys_to_remove:
                cls._token_cache.pop(key, None)
        else:
            cls._token_cache.clear()
        logger.debug("MS Graph token cache cleared")

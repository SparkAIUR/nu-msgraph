"""Tests for MSGraphSubscriptionService."""

import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

from nu_msgraph import (
    MSGraphClient,
    MSGraphConfig,
    MSGraphCrypto,
    MSGraphSubscriptionService,
    MSGraphError,
    MSGraphConfigError,
    MSGraphSubscriptionError,
)


@pytest.fixture
def config():
    """Create test configuration."""
    return MSGraphConfig(
        tenant_id="test-tenant-id",
        client_id="test-client-id",
        client_secret="test-client-secret",
        from_address="sender@test.com",
        webhook_url="https://test.example.com/webhook",
    )


@pytest.fixture
def client(config):
    """Create test client."""
    return MSGraphClient(config)


@pytest.fixture
def subscription_service(client, config):
    """Create test subscription service."""
    return MSGraphSubscriptionService(client, config)


@pytest.fixture
def mock_token_response():
    """Create mock token response."""
    return {
        "access_token": "test-access-token",
        "token_type": "Bearer",
        "expires_in": 3600,
    }


class TestMSGraphSubscriptionServiceCreate:
    """Test subscription creation."""

    @pytest.mark.asyncio
    async def test_create_subscription_success(
        self, subscription_service, mock_token_response
    ):
        """Test successful subscription creation."""
        MSGraphClient.clear_token_cache()

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        create_response = MagicMock()
        create_response.status_code = 201
        create_response.content = b"{}"
        create_response.json.return_value = {
            "id": "subscription-123",
            "resource": "/users/sender@test.com/messages",
            "changeType": "created",
            "notificationUrl": "https://test.example.com/webhook",
            "expirationDateTime": "2024-01-01T00:00:00Z",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.side_effect = [token_response, create_response]
            mock_client.return_value.__aenter__.return_value = mock_http

            result = await subscription_service.create_subscription(
                change_types=["created"],
                expiration_hours=72,
            )

            assert result["subscription_id"] == "subscription-123"
            assert result["user_email"] == "sender@test.com"
            assert result["notification_url"] == "https://test.example.com/webhook"

    @pytest.mark.asyncio
    async def test_create_subscription_no_webhook_url(self, client):
        """Test subscription creation without webhook URL."""
        config = MSGraphConfig(
            tenant_id="test",
            client_id="test",
            client_secret="test",
            from_address="test@test.com",
            # No webhook_url
        )
        service = MSGraphSubscriptionService(client, config)

        with pytest.raises(MSGraphConfigError) as exc_info:
            await service.create_subscription()

        assert "webhook" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_create_subscription_with_rich_notifications(
        self, client, config, mock_token_response
    ):
        """Test subscription with Rich Notifications enabled."""
        MSGraphClient.clear_token_cache()

        # Setup crypto
        crypto = MSGraphCrypto()
        crypto.generate_certificate()
        service = MSGraphSubscriptionService(client, config, crypto=crypto)

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        create_response = MagicMock()
        create_response.status_code = 201
        create_response.content = b"{}"
        create_response.json.return_value = {
            "id": "rich-subscription-123",
            "resource": "/users/sender@test.com/messages",
            "changeType": "created",
            "notificationUrl": "https://test.example.com/webhook",
            "expirationDateTime": "2024-01-01T00:00:00Z",
            "includeResourceData": True,
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.side_effect = [token_response, create_response]
            mock_client.return_value.__aenter__.return_value = mock_http

            result = await service.create_subscription(
                include_resource_data=True,
            )

            assert result["subscription_id"] == "rich-subscription-123"
            assert result["include_resource_data"] is True

            # Verify the payload included encryption certificate
            call_args = mock_http.post.call_args_list[1]
            payload = call_args.kwargs["json"]
            assert "encryptionCertificate" in payload
            assert "encryptionCertificateId" in payload


class TestMSGraphSubscriptionServiceRenew:
    """Test subscription renewal."""

    @pytest.mark.asyncio
    async def test_renew_subscription_success(
        self, subscription_service, mock_token_response
    ):
        """Test successful subscription renewal."""
        MSGraphClient.clear_token_cache()

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        renew_response = MagicMock()
        renew_response.status_code = 200
        renew_response.content = b"{}"
        renew_response.json.return_value = {
            "id": "subscription-123",
            "expirationDateTime": "2024-01-04T00:00:00Z",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = token_response
            mock_http.patch.return_value = renew_response
            mock_client.return_value.__aenter__.return_value = mock_http

            result = await subscription_service.renew_subscription("subscription-123")

            assert result["subscription_id"] == "subscription-123"
            assert result["renewed"] is True

    @pytest.mark.asyncio
    async def test_renew_subscription_not_found(
        self, subscription_service, mock_token_response
    ):
        """Test renewal of non-existent subscription."""
        MSGraphClient.clear_token_cache()

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        renew_response = MagicMock()
        renew_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = token_response
            mock_http.patch.return_value = renew_response
            mock_client.return_value.__aenter__.return_value = mock_http

            with pytest.raises(MSGraphSubscriptionError) as exc_info:
                await subscription_service.renew_subscription("nonexistent")

            assert exc_info.value.code == "subscription_not_found"


class TestMSGraphSubscriptionServiceDelete:
    """Test subscription deletion."""

    @pytest.mark.asyncio
    async def test_delete_subscription_success(
        self, subscription_service, mock_token_response
    ):
        """Test successful subscription deletion."""
        MSGraphClient.clear_token_cache()

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        delete_response = MagicMock()
        delete_response.status_code = 204

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = token_response
            mock_http.delete.return_value = delete_response
            mock_client.return_value.__aenter__.return_value = mock_http

            result = await subscription_service.delete_subscription("subscription-123")

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_subscription_not_found_returns_true(
        self, subscription_service, mock_token_response
    ):
        """Test deletion of non-existent subscription returns True."""
        MSGraphClient.clear_token_cache()

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        delete_response = MagicMock()
        delete_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = token_response
            mock_http.delete.return_value = delete_response
            mock_client.return_value.__aenter__.return_value = mock_http

            # Should return True even for 404 (already deleted)
            result = await subscription_service.delete_subscription("nonexistent")
            assert result is True


class TestMSGraphSubscriptionServiceList:
    """Test subscription listing."""

    @pytest.mark.asyncio
    async def test_list_subscriptions_success(
        self, subscription_service, mock_token_response
    ):
        """Test successful subscription listing."""
        MSGraphClient.clear_token_cache()

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.content = b"{}"
        list_response.json.return_value = {
            "value": [
                {"id": "sub-1", "resource": "/users/test@test.com/messages"},
                {"id": "sub-2", "resource": "/users/other@test.com/messages"},
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = token_response
            mock_http.get.return_value = list_response
            mock_client.return_value.__aenter__.return_value = mock_http

            subscriptions = await subscription_service.list_subscriptions()

            assert len(subscriptions) == 2
            assert subscriptions[0]["id"] == "sub-1"


class TestMSGraphSubscriptionServiceHelpers:
    """Test helper methods."""

    def test_needs_renewal_string_expiration(self, subscription_service):
        """Test needs_renewal with string expiration."""
        # Expires in 12 hours (within 24 hour buffer)
        soon = datetime.now(UTC) + timedelta(hours=12)
        assert subscription_service.needs_renewal(soon.isoformat()) is True

        # Expires in 48 hours (outside 24 hour buffer)
        later = datetime.now(UTC) + timedelta(hours=48)
        assert subscription_service.needs_renewal(later.isoformat()) is False

    def test_needs_renewal_datetime_expiration(self, subscription_service):
        """Test needs_renewal with datetime expiration."""
        soon = datetime.now(UTC) + timedelta(hours=12)
        assert subscription_service.needs_renewal(soon) is True

        later = datetime.now(UTC) + timedelta(hours=48)
        assert subscription_service.needs_renewal(later) is False

    def test_needs_renewal_iso_format_with_z(self, subscription_service):
        """Test needs_renewal with ISO format ending in Z."""
        soon = datetime.now(UTC) + timedelta(hours=12)
        iso_str = soon.isoformat().replace("+00:00", "Z")
        assert subscription_service.needs_renewal(iso_str) is True

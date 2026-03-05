"""Tests for MSGraphClient."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

from nu_msgraph import (
    MSGraphClient,
    MSGraphConfig,
    MSGraphError,
    MSGraphAuthError,
    MSGraphConfigError,
    MSGraphNetworkError,
)


@pytest.fixture
def config():
    """Create test configuration."""
    return MSGraphConfig(
        tenant_id="test-tenant-id",
        client_id="test-client-id",
        client_secret="test-client-secret",
        from_address="sender@test.com",
    )


@pytest.fixture
def client(config):
    """Create test client."""
    return MSGraphClient(config)


@pytest.fixture
def mock_token_response():
    """Create mock token response."""
    return {
        "access_token": "test-access-token-12345",
        "token_type": "Bearer",
        "expires_in": 3600,
    }


class TestMSGraphClientConfiguration:
    """Test client configuration."""

    def test_client_from_config(self, config):
        """Test client creation from config."""
        client = MSGraphClient(config)
        assert client.is_configured
        assert client.is_enabled

    def test_client_default_config(self):
        """Test client with default (empty) config."""
        # Clear any env vars that might be set
        with patch.dict("os.environ", {}, clear=True):
            client = MSGraphClient()
            # Will be unconfigured since no env vars
            assert not client.is_configured

    def test_client_disabled(self, config):
        """Test disabled client."""
        config.enabled = False
        client = MSGraphClient(config)
        assert client.is_configured
        assert not client.is_enabled


class TestMSGraphClientTokenManagement:
    """Test token acquisition and caching."""

    @pytest.mark.asyncio
    async def test_get_access_token_success(self, client, mock_token_response):
        """Test successful token acquisition."""
        # Clear any cached tokens
        MSGraphClient.clear_token_cache()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_token_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            token = await client._get_access_token()
            assert token == "test-access-token-12345"

    @pytest.mark.asyncio
    async def test_get_access_token_cached(self, client, mock_token_response):
        """Test token caching."""
        MSGraphClient.clear_token_cache()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_token_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_http

            # First call - should fetch token
            token1 = await client._get_access_token()
            
            # Second call - should use cached token
            token2 = await client._get_access_token()

            assert token1 == token2
            # Should only call post once (token is cached)
            assert mock_http.post.call_count == 1

    @pytest.mark.asyncio
    async def test_get_access_token_auth_failure(self, client):
        """Test authentication failure."""
        MSGraphClient.clear_token_cache()

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.content = b'{"error": "invalid_client", "error_description": "Bad credentials"}'
        mock_response.json.return_value = {
            "error": "invalid_client",
            "error_description": "Bad credentials",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(MSGraphAuthError) as exc_info:
                await client._get_access_token()

            assert "Bad credentials" in str(exc_info.value)
            assert exc_info.value.code == "invalid_client"

    @pytest.mark.asyncio
    async def test_get_access_token_network_error(self, client):
        """Test network error during token acquisition."""
        MSGraphClient.clear_token_cache()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.RequestError("Connection failed")
            )

            with pytest.raises(MSGraphNetworkError):
                await client._get_access_token()


class TestMSGraphClientSendEmail:
    """Test email sending."""

    @pytest.mark.asyncio
    async def test_send_email_success(self, client, mock_token_response):
        """Test successful email sending."""
        MSGraphClient.clear_token_cache()

        # Mock token response
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        # Mock send email response
        send_response = MagicMock()
        send_response.status_code = 202
        send_response.headers = {"request-id": "test-request-id"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.side_effect = [token_response, send_response]
            mock_client.return_value.__aenter__.return_value = mock_http

            result = await client.send_email(
                to_address="recipient@test.com",
                subject="Test Subject",
                body_text="Test body",
            )

            assert result["status"] == "sent"
            assert result["request_id"] == "test-request-id"
            assert result["to"] == "recipient@test.com"
            assert result["subject"] == "Test Subject"

    @pytest.mark.asyncio
    async def test_send_email_not_enabled(self):
        """Test send email when not enabled."""
        config = MSGraphConfig(enabled=False)
        client = MSGraphClient(config)

        with pytest.raises(MSGraphConfigError) as exc_info:
            await client.send_email(
                to_address="recipient@test.com",
                subject="Test",
                body_text="Test",
            )

        assert "not enabled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_send_email_html(self, client, mock_token_response):
        """Test sending HTML email."""
        MSGraphClient.clear_token_cache()

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        send_response = MagicMock()
        send_response.status_code = 202
        send_response.headers = {"request-id": "html-request-id"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.side_effect = [token_response, send_response]
            mock_client.return_value.__aenter__.return_value = mock_http

            result = await client.send_email(
                to_address="recipient@test.com",
                subject="HTML Test",
                body_text="Fallback text",
                body_html="<h1>Hello</h1>",
            )

            assert result["status"] == "sent"

            # Verify the payload had HTML content type
            call_args = mock_http.post.call_args_list[1]  # Second call is send email
            payload = call_args.kwargs["json"]
            assert payload["message"]["body"]["contentType"] == "HTML"
            assert payload["message"]["body"]["content"] == "<h1>Hello</h1>"


class TestMSGraphClientListMessages:
    """Test message listing."""

    @pytest.mark.asyncio
    async def test_list_messages_success(self, client, mock_token_response):
        """Test successful message listing."""
        MSGraphClient.clear_token_cache()

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = {
            "value": [
                {"id": "msg1", "subject": "Test 1"},
                {"id": "msg2", "subject": "Test 2"},
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = token_response
            mock_http.get.return_value = list_response
            mock_client.return_value.__aenter__.return_value = mock_http

            messages = await client.list_messages(top=5)

            assert len(messages) == 2
            assert messages[0]["id"] == "msg1"
            assert messages[1]["subject"] == "Test 2"


class TestMSGraphClientGetMessage:
    """Test single message retrieval."""

    @pytest.mark.asyncio
    async def test_get_message_success(self, client, mock_token_response):
        """Test successful message retrieval."""
        MSGraphClient.clear_token_cache()

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            "id": "test-message-id",
            "subject": "Test Subject",
            "body": {"contentType": "Text", "content": "Hello"},
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = token_response
            mock_http.get.return_value = get_response
            mock_client.return_value.__aenter__.return_value = mock_http

            message = await client.get_message("test-message-id")

            assert message["id"] == "test-message-id"
            assert message["subject"] == "Test Subject"

    @pytest.mark.asyncio
    async def test_get_message_not_found(self, client, mock_token_response):
        """Test message not found."""
        MSGraphClient.clear_token_cache()

        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = mock_token_response

        get_response = MagicMock()
        get_response.status_code = 404

        with patch("httpx.AsyncClient") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = token_response
            mock_http.get.return_value = get_response
            mock_client.return_value.__aenter__.return_value = mock_http

            with pytest.raises(MSGraphError) as exc_info:
                await client.get_message("nonexistent-id")

            assert exc_info.value.code == "message_not_found"
            assert exc_info.value.status_code == 404


class TestMSGraphClientHelpers:
    """Test helper methods."""

    def test_mask_email(self):
        """Test email masking."""
        assert MSGraphClient._mask_email("test@example.com") == "te***@example.com"
        assert MSGraphClient._mask_email("a@b.com") == "a***@b.com"
        assert MSGraphClient._mask_email("no-at-sign") == "no***"

    def test_clear_token_cache(self, config):
        """Test clearing token cache."""
        # Add some fake tokens
        MSGraphClient._token_cache["test-tenant:test-client"] = ("token", 9999999999)
        MSGraphClient._token_cache["other-tenant:other-client"] = ("token2", 9999999999)

        # Clear specific tenant
        MSGraphClient.clear_token_cache("test-tenant")
        assert "test-tenant:test-client" not in MSGraphClient._token_cache
        assert "other-tenant:other-client" in MSGraphClient._token_cache

        # Clear all
        MSGraphClient.clear_token_cache()
        assert len(MSGraphClient._token_cache) == 0

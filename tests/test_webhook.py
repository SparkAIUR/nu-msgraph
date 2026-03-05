"""Tests for BaseWebhookHandler."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from nu_msgraph import (
    BaseWebhookHandler,
    LoggingWebhookHandler,
    ChangeNotification,
    MSGraphConfig,
    MSGraphCrypto,
)
from nu_msgraph.webhook import WebhookResponse


class ConcreteWebhookHandler(BaseWebhookHandler):
    """Concrete implementation for testing."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.created_notifications = []
        self.updated_notifications = []
        self.deleted_notifications = []
    
    async def on_email_created(self, notification: ChangeNotification) -> None:
        self.created_notifications.append(notification)
    
    async def on_email_updated(self, notification: ChangeNotification) -> None:
        self.updated_notifications.append(notification)
    
    async def on_email_deleted(self, notification: ChangeNotification) -> None:
        self.deleted_notifications.append(notification)


@pytest.fixture
def handler():
    """Create test handler."""
    return ConcreteWebhookHandler()


class TestWebhookResponse:
    """Test WebhookResponse class."""
    
    def test_validation_response(self):
        """Test validation response creation."""
        response = WebhookResponse.validation_response("test-token")
        assert response.content == "test-token"
        assert response.status_code == 200
        assert response.media_type == "text/plain"
    
    def test_accepted_response(self):
        """Test accepted response creation."""
        response = WebhookResponse.accepted()
        assert response.content == ""
        assert response.status_code == 202
    
    def test_error_response(self):
        """Test error response creation."""
        response = WebhookResponse.error("Something went wrong", 400)
        assert response.content == "Something went wrong"
        assert response.status_code == 400


class TestBaseWebhookHandlerValidation:
    """Test webhook validation handling."""
    
    @pytest.mark.asyncio
    async def test_process_validation_request_dict(self, handler):
        """Test processing validation request with dict body."""
        result = await handler.process_request(
            request={},
            query_params={"validationToken": "my-validation-token"},
        )
        
        assert result.status_code == 200
        assert result.content == "my-validation-token"
    
    @pytest.mark.asyncio
    async def test_process_validation_request_mock_request(self, handler):
        """Test processing validation request with mock request object."""
        mock_request = MagicMock()
        mock_request.query_params = {"validationToken": "request-token"}
        
        result = await handler.process_request(mock_request)
        
        assert result.status_code == 200
        assert result.content == "request-token"


class TestBaseWebhookHandlerNotifications:
    """Test notification processing."""
    
    @pytest.mark.asyncio
    async def test_process_created_notification(self, handler):
        """Test processing created notification."""
        body = {
            "value": [
                {
                    "subscriptionId": "sub-123",
                    "changeType": "created",
                    "resource": "/users/test@test.com/messages",
                    "resourceData": {
                        "id": "message-456",
                        "@odata.type": "#Microsoft.Graph.Message",
                    },
                }
            ]
        }
        
        result = await handler.process_request(body, query_params={})
        
        assert result.status_code == 202
        assert len(handler.created_notifications) == 1
        assert handler.created_notifications[0].message_id == "message-456"
    
    @pytest.mark.asyncio
    async def test_process_updated_notification(self, handler):
        """Test processing updated notification."""
        body = {
            "value": [
                {
                    "subscriptionId": "sub-123",
                    "changeType": "updated",
                    "resourceData": {"id": "message-789"},
                }
            ]
        }
        
        await handler.process_request(body, query_params={})
        
        assert len(handler.updated_notifications) == 1
        assert handler.updated_notifications[0].message_id == "message-789"
    
    @pytest.mark.asyncio
    async def test_process_deleted_notification(self, handler):
        """Test processing deleted notification."""
        body = {
            "value": [
                {
                    "subscriptionId": "sub-123",
                    "changeType": "deleted",
                    "resourceData": {"id": "message-deleted"},
                }
            ]
        }
        
        await handler.process_request(body, query_params={})
        
        assert len(handler.deleted_notifications) == 1
    
    @pytest.mark.asyncio
    async def test_process_multiple_notifications(self, handler):
        """Test processing multiple notifications at once."""
        body = {
            "value": [
                {"changeType": "created", "resourceData": {"id": "msg-1"}},
                {"changeType": "created", "resourceData": {"id": "msg-2"}},
                {"changeType": "updated", "resourceData": {"id": "msg-3"}},
            ]
        }
        
        result = await handler.process_request(body, query_params={})
        
        assert result.status_code == 202
        assert len(handler.created_notifications) == 2
        assert len(handler.updated_notifications) == 1


class TestBaseWebhookHandlerClientStateValidation:
    """Test client state validation."""
    
    @pytest.mark.asyncio
    async def test_validate_client_state_valid(self):
        """Test with valid client state."""
        handler = ConcreteWebhookHandler(
            validate_client_state=True,
            expected_client_states={"valid-state"},
        )
        
        body = {
            "value": [
                {
                    "changeType": "created",
                    "clientState": "valid-state",
                    "resourceData": {"id": "msg-1"},
                }
            ]
        }
        
        await handler.process_request(body, query_params={})
        
        assert len(handler.created_notifications) == 1
    
    @pytest.mark.asyncio
    async def test_validate_client_state_invalid(self):
        """Test with invalid client state."""
        handler = ConcreteWebhookHandler(
            validate_client_state=True,
            expected_client_states={"valid-state"},
        )
        
        body = {
            "value": [
                {
                    "changeType": "created",
                    "clientState": "invalid-state",
                    "resourceData": {"id": "msg-1"},
                }
            ]
        }
        
        await handler.process_request(body, query_params={})
        
        # Should not process notification with invalid state
        assert len(handler.created_notifications) == 0


class TestBaseWebhookHandlerRichNotifications:
    """Test Rich Notification handling."""
    
    @pytest.mark.asyncio
    async def test_rich_notification_decryption(self):
        """Test that Rich Notifications are decrypted when crypto is configured."""
        from cryptography.hazmat.primitives import hashes, padding
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        import base64
        import json
        import hmac
        import os
        
        # Setup crypto
        crypto = MSGraphCrypto()
        crypto.generate_certificate()
        
        handler = ConcreteWebhookHandler(crypto=crypto)
        
        # Create encrypted content
        public_key = crypto._certificate.public_key()
        test_data = {"subject": "Secret Email", "body": "Secret content"}
        plaintext = json.dumps(test_data).encode()
        
        symmetric_key = os.urandom(32)
        iv = os.urandom(16)
        
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext) + padder.finalize()
        
        cipher = Cipher(algorithms.AES(symmetric_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        encrypted_data = iv + ciphertext
        encrypted_key = public_key.encrypt(
            symmetric_key,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        signature = hmac.new(symmetric_key, encrypted_data, "sha256").digest()
        
        body = {
            "value": [
                {
                    "changeType": "created",
                    "resourceData": {"id": "msg-encrypted"},
                    "encryptedContent": {
                        "data": base64.b64encode(encrypted_data).decode(),
                        "dataKey": base64.b64encode(encrypted_key).decode(),
                        "dataSignature": base64.b64encode(signature).decode(),
                        "encryptionCertificateId": crypto.get_certificate_id(),
                    },
                }
            ]
        }
        
        await handler.process_request(body, query_params={})
        
        assert len(handler.created_notifications) == 1
        notification = handler.created_notifications[0]
        assert notification.decrypted_content is not None
        assert notification.decrypted_content["subject"] == "Secret Email"


class TestLoggingWebhookHandler:
    """Test LoggingWebhookHandler."""
    
    @pytest.mark.asyncio
    async def test_logging_handler_processes_all_types(self):
        """Test that logging handler processes all notification types."""
        handler = LoggingWebhookHandler()
        
        body = {
            "value": [
                {"changeType": "created", "resourceData": {"id": "msg-1"}},
                {"changeType": "updated", "resourceData": {"id": "msg-2"}},
                {"changeType": "deleted", "resourceData": {"id": "msg-3"}},
            ]
        }
        
        # Should not raise
        result = await handler.process_request(body, query_params={})
        assert result.status_code == 202


class TestChangeNotificationModel:
    """Test ChangeNotification model."""
    
    def test_message_id_property(self):
        """Test message_id property extraction."""
        notification = ChangeNotification(
            changeType="created",
            resourceData={"id": "test-message-id"},
        )
        
        assert notification.message_id == "test-message-id"
    
    def test_is_rich_notification_true(self):
        """Test is_rich_notification property when encrypted."""
        notification = ChangeNotification(
            changeType="created",
            encryptedContent={"data": "x", "dataKey": "y"},
        )
        
        assert notification.is_rich_notification is True
    
    def test_is_rich_notification_false(self):
        """Test is_rich_notification property when not encrypted."""
        notification = ChangeNotification(
            changeType="created",
            resourceData={"id": "msg"},
        )
        
        assert notification.is_rich_notification is False

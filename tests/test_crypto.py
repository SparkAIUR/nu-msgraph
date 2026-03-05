"""Tests for MSGraphCrypto."""

import base64
import json
import pytest

from nu_msgraph import MSGraphCrypto, MSGraphConfig, MSGraphCryptoError


class TestMSGraphCryptoGeneration:
    """Test certificate generation."""

    def test_generate_certificate(self):
        """Test certificate generation."""
        crypto = MSGraphCrypto()
        
        private_key_pem, certificate_pem, cert_id = crypto.generate_certificate(
            common_name="Test Certificate",
            organization="Test Org",
            validity_days=30,
        )
        
        assert private_key_pem.startswith(b"-----BEGIN PRIVATE KEY-----")
        assert certificate_pem.startswith(b"-----BEGIN CERTIFICATE-----")
        assert len(cert_id) == 32  # UUID hex

    def test_generate_certificate_sets_internal_state(self):
        """Test that generation sets internal state."""
        crypto = MSGraphCrypto()
        
        assert not crypto.is_configured()
        
        crypto.generate_certificate()
        
        assert crypto.is_configured()

    def test_get_certificate_base64(self):
        """Test getting base64 certificate for subscription."""
        crypto = MSGraphCrypto()
        crypto.generate_certificate()
        
        cert_b64 = crypto.get_certificate_base64()
        
        # Should be valid base64
        decoded = base64.b64decode(cert_b64)
        assert len(decoded) > 0

    def test_get_certificate_id(self):
        """Test getting certificate ID."""
        crypto = MSGraphCrypto()
        _, _, expected_id = crypto.generate_certificate()
        
        assert crypto.get_certificate_id() == expected_id


class TestMSGraphCryptoLoading:
    """Test certificate loading."""

    def test_load_certificate(self):
        """Test loading existing certificate."""
        # First generate a certificate
        crypto1 = MSGraphCrypto()
        private_key_pem, certificate_pem, cert_id = crypto1.generate_certificate()
        
        # Load into new instance
        crypto2 = MSGraphCrypto()
        crypto2.load_certificate(private_key_pem, certificate_pem, cert_id)
        
        assert crypto2.is_configured()
        assert crypto2.get_certificate_id() == cert_id

    def test_from_config(self):
        """Test loading from config."""
        # Generate certificate
        crypto_gen = MSGraphCrypto()
        private_key_pem, certificate_pem, cert_id = crypto_gen.generate_certificate()
        
        # Create config with base64-encoded values
        config = MSGraphConfig(
            tenant_id="test",
            client_id="test",
            client_secret="test",
            from_address="test@test.com",
            private_key=base64.b64encode(private_key_pem).decode(),
            certificate=base64.b64encode(certificate_pem).decode(),
            certificate_id=cert_id,
        )
        
        # Load from config
        crypto = MSGraphCrypto.from_config(config)
        
        assert crypto.is_configured()
        assert crypto.get_certificate_id() == cert_id


class TestMSGraphCryptoDecryption:
    """Test notification decryption."""

    def test_decrypt_notification(self):
        """Test decrypting a notification payload.
        
        This test creates a mock encrypted payload similar to what
        Microsoft Graph would send.
        """
        from cryptography.hazmat.primitives import hashes, padding
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        import hmac
        import os
        
        # Generate certificate
        crypto = MSGraphCrypto()
        crypto.generate_certificate()
        
        # Get the public key for encryption
        public_key = crypto._certificate.public_key()
        
        # Create test payload
        test_data = {
            "subject": "Test Email",
            "from": {"emailAddress": {"address": "sender@test.com"}},
        }
        plaintext = json.dumps(test_data).encode()
        
        # Generate random AES-256 key
        symmetric_key = os.urandom(32)
        
        # Generate random IV
        iv = os.urandom(16)
        
        # Pad plaintext
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext) + padder.finalize()
        
        # Encrypt with AES-256-CBC
        cipher = Cipher(
            algorithms.AES(symmetric_key),
            modes.CBC(iv),
            backend=default_backend(),
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        # Prepend IV to ciphertext
        encrypted_data = iv + ciphertext
        
        # Encrypt symmetric key with RSA-OAEP
        encrypted_key = public_key.encrypt(
            symmetric_key,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        
        # Generate HMAC signature
        signature = hmac.new(symmetric_key, encrypted_data, "sha256").digest()
        
        # Build encrypted content payload
        encrypted_content = {
            "data": base64.b64encode(encrypted_data).decode(),
            "dataKey": base64.b64encode(encrypted_key).decode(),
            "dataSignature": base64.b64encode(signature).decode(),
            "encryptionCertificateId": crypto.get_certificate_id(),
        }
        
        # Decrypt
        decrypted = crypto.decrypt_notification(encrypted_content)
        
        assert decrypted["subject"] == "Test Email"
        assert decrypted["from"]["emailAddress"]["address"] == "sender@test.com"

    def test_decrypt_notification_not_configured(self):
        """Test decryption when not configured."""
        crypto = MSGraphCrypto()
        
        with pytest.raises(MSGraphCryptoError) as exc_info:
            crypto.decrypt_notification({"data": "test", "dataKey": "test"})
        
        assert "not loaded" in str(exc_info.value).lower()

    def test_decrypt_notification_missing_data(self):
        """Test decryption with missing data."""
        crypto = MSGraphCrypto()
        crypto.generate_certificate()
        
        with pytest.raises(MSGraphCryptoError) as exc_info:
            crypto.decrypt_notification({"data": "test"})  # Missing dataKey
        
        assert "missing" in str(exc_info.value).lower()

    def test_get_certificate_not_configured(self):
        """Test getting certificate when not configured."""
        crypto = MSGraphCrypto()
        
        with pytest.raises(MSGraphCryptoError):
            crypto.get_certificate_base64()
        
        with pytest.raises(MSGraphCryptoError):
            crypto.get_certificate_id()


class TestMSGraphCryptoEnvVars:
    """Test environment variable generation."""

    def test_get_env_vars_for_config(self):
        """Test getting environment variable values."""
        crypto = MSGraphCrypto()
        crypto.generate_certificate()
        
        env_vars = crypto.get_env_vars_for_config()
        
        assert "MS_GRAPH_PRIVATE_KEY" in env_vars
        assert "MS_GRAPH_CERTIFICATE" in env_vars
        assert "MS_GRAPH_CERTIFICATE_ID" in env_vars
        
        # Values should be base64
        base64.b64decode(env_vars["MS_GRAPH_PRIVATE_KEY"])
        base64.b64decode(env_vars["MS_GRAPH_CERTIFICATE"])

    def test_get_env_vars_not_configured(self):
        """Test getting env vars when not configured."""
        crypto = MSGraphCrypto()
        
        with pytest.raises(MSGraphCryptoError):
            crypto.get_env_vars_for_config()

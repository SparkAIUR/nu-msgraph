"""Microsoft Graph API Rich Notifications encryption/decryption.

This module handles:
- Certificate generation for Rich Notifications
- Decrypting encryptedContent from webhook payloads
- Key management and storage

Rich Notifications Flow:
1. Generate RSA key pair (private key stored securely, public cert sent to Graph)
2. When creating subscription, include base64-encoded public certificate
3. Graph encrypts notification data with symmetric key (AES-256-CBC)
4. Symmetric key is encrypted with our public key (RSA-OAEP-256)
5. We decrypt symmetric key with private key, then decrypt data with symmetric key

References:
- Rich Notifications: https://learn.microsoft.com/en-us/graph/change-notifications-with-resource-data
- Encryption: https://learn.microsoft.com/en-us/graph/webhooks-with-resource-data
"""

from __future__ import annotations

import base64
import hmac
import json
from datetime import datetime, timedelta, UTC
from typing import Any
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.x509.oid import NameOID

from nu_msgraph.config import MSGraphConfig, logger
from nu_msgraph.exceptions import MSGraphCryptoError


class MSGraphCrypto:
    """Handle Rich Notifications encryption for Microsoft Graph.
    
    Manages certificate generation, storage, and decryption of
    encrypted webhook payloads.
    
    Example:
        # Generate new certificate
        crypto = MSGraphCrypto()
        private_key, cert, cert_id = crypto.generate_certificate()
        
        # Load existing certificate
        crypto = MSGraphCrypto()
        crypto.load_certificate(private_key_pem, certificate_pem, cert_id)
        
        # Or load from config/environment
        config = MSGraphConfig()  # Loads from env
        crypto = MSGraphCrypto.from_config(config)
    """

    # RSA key size for encryption
    RSA_KEY_SIZE = 2048

    # Certificate validity period
    CERT_VALIDITY_DAYS = 365

    def __init__(self) -> None:
        """Initialize crypto service."""
        self._private_key: rsa.RSAPrivateKey | None = None
        self._certificate: x509.Certificate | None = None
        self._cert_id: str | None = None

    @classmethod
    def from_config(cls, config: MSGraphConfig) -> "MSGraphCrypto":
        """Create crypto service from configuration.
        
        Args:
            config: MSGraphConfig with certificate settings.
            
        Returns:
            Configured MSGraphCrypto instance.
        """
        crypto = cls()
        if config.has_crypto_config():
            try:
                private_key_pem = base64.b64decode(config.private_key)
                certificate_pem = base64.b64decode(config.certificate)
                crypto.load_certificate(private_key_pem, certificate_pem, config.certificate_id)
            except Exception as e:
                logger.error(f"Failed to load certificate from config: {e}")
        return crypto

    def generate_certificate(
        self,
        common_name: str = "MS Graph Notifications",
        organization: str = "NU MsgGraph",
        validity_days: int | None = None,
    ) -> tuple[bytes, bytes, str]:
        """Generate a new RSA key pair and self-signed certificate.
        
        Args:
            common_name: Certificate common name (CN).
            organization: Organization name for certificate.
            validity_days: Certificate validity in days.
            
        Returns:
            Tuple of (private_key_pem, certificate_pem, certificate_id)
        """
        validity = validity_days or self.CERT_VALIDITY_DAYS

        # Generate RSA private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.RSA_KEY_SIZE,
            backend=default_backend(),
        )

        # Generate certificate ID
        cert_id = uuid4().hex

        # Build certificate subject
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])

        # Build self-signed certificate
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC))
            .not_valid_after(datetime.now(UTC) + timedelta(days=validity))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    content_commitment=False,
                    data_encipherment=True,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(private_key, hashes.SHA256(), default_backend())
        )

        # Serialize to PEM format
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        certificate_pem = cert.public_bytes(serialization.Encoding.PEM)

        # Cache for later use
        self._private_key = private_key
        self._certificate = cert
        self._cert_id = cert_id

        logger.info(f"Generated MS Graph certificate: {cert_id}")

        return private_key_pem, certificate_pem, cert_id

    def load_certificate(
        self,
        private_key_pem: bytes,
        certificate_pem: bytes,
        cert_id: str,
    ) -> None:
        """Load existing certificate and private key.
        
        Args:
            private_key_pem: PEM-encoded private key.
            certificate_pem: PEM-encoded certificate.
            cert_id: Certificate ID used in subscriptions.
        """
        self._private_key = serialization.load_pem_private_key(
            private_key_pem,
            password=None,
            backend=default_backend(),
        )

        self._certificate = x509.load_pem_x509_certificate(
            certificate_pem,
            backend=default_backend(),
        )

        self._cert_id = cert_id

        logger.info(f"Loaded MS Graph certificate: {cert_id}")

    def is_configured(self) -> bool:
        """Check if certificate is loaded and ready for use."""
        return all([self._private_key, self._certificate, self._cert_id])

    def get_certificate_base64(self) -> str:
        """Get base64-encoded certificate for subscription creation.
        
        Returns:
            Base64-encoded DER certificate (no PEM headers).
            
        Raises:
            MSGraphCryptoError: If certificate not loaded.
        """
        if not self._certificate:
            raise MSGraphCryptoError("Certificate not loaded", code="not_configured")

        # Graph API expects DER-encoded certificate in base64
        der_bytes = self._certificate.public_bytes(serialization.Encoding.DER)
        return base64.b64encode(der_bytes).decode("ascii")

    def get_certificate_id(self) -> str:
        """Get certificate ID for subscription creation.
        
        Returns:
            Certificate ID string.
            
        Raises:
            MSGraphCryptoError: If certificate not loaded.
        """
        if not self._cert_id:
            raise MSGraphCryptoError("Certificate not loaded", code="not_configured")
        return self._cert_id

    def decrypt_notification(self, encrypted_content: dict[str, Any]) -> dict[str, Any]:
        """Decrypt Rich Notification encryptedContent payload.
        
        Graph encrypts data as follows:
        1. Generate random AES-256 key (dataKey)
        2. Encrypt notification data with AES-256-CBC using dataKey
        3. Encrypt dataKey with our public key using RSA-OAEP-256
        4. Send us: encryptedKey (base64), data (base64), dataSignature (HMAC-SHA256)
        
        Args:
            encrypted_content: The encryptedContent object from notification.
                Expected keys: data, dataKey, dataSignature, encryptionCertificateId
                
        Returns:
            Decrypted notification data as dictionary.
            
        Raises:
            MSGraphCryptoError: If decryption fails.
        """
        if not self._private_key:
            raise MSGraphCryptoError("Private key not loaded", code="not_configured")

        try:
            # Extract encrypted components
            encrypted_data_b64 = encrypted_content.get("data")
            encrypted_key_b64 = encrypted_content.get("dataKey")
            data_signature_b64 = encrypted_content.get("dataSignature")
            cert_id = encrypted_content.get("encryptionCertificateId")

            if not all([encrypted_data_b64, encrypted_key_b64]):
                raise MSGraphCryptoError("Missing encrypted data or key", code="invalid_payload")

            # Verify certificate ID matches
            if cert_id and cert_id != self._cert_id:
                logger.warning(f"Certificate ID mismatch: expected {self._cert_id}, got {cert_id}")

            # Decode base64 values
            encrypted_key = base64.b64decode(encrypted_key_b64)
            encrypted_data = base64.b64decode(encrypted_data_b64)

            # Decrypt the symmetric key using our private key (RSA-OAEP-256)
            symmetric_key = self._private_key.decrypt(
                encrypted_key,
                asym_padding.OAEP(
                    mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            # Validate signature if provided
            if data_signature_b64:
                self._verify_signature(encrypted_data, symmetric_key, data_signature_b64)

            # Decrypt the data using AES-256-CBC
            # First 16 bytes of encrypted data is the IV
            iv = encrypted_data[:16]
            ciphertext = encrypted_data[16:]

            cipher = Cipher(
                algorithms.AES(symmetric_key),
                modes.CBC(iv),
                backend=default_backend(),
            )
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(ciphertext) + decryptor.finalize()

            # Remove PKCS7 padding
            unpadder = padding.PKCS7(128).unpadder()
            decrypted_data = unpadder.update(padded_data) + unpadder.finalize()

            # Parse JSON
            return json.loads(decrypted_data.decode("utf-8"))

        except MSGraphCryptoError:
            raise
        except json.JSONDecodeError as e:
            raise MSGraphCryptoError(
                f"Failed to parse decrypted JSON: {e}", code="parse_error"
            ) from e
        except Exception as e:
            logger.error(f"Notification decryption failed: {e}")
            raise MSGraphCryptoError(f"Decryption failed: {e}", code="decrypt_error") from e

    def _verify_signature(
        self,
        encrypted_data: bytes,
        symmetric_key: bytes,
        signature_b64: str,
    ) -> None:
        """Verify HMAC-SHA256 signature of encrypted data.
        
        Args:
            encrypted_data: The encrypted data bytes.
            symmetric_key: The decrypted symmetric key.
            signature_b64: Base64-encoded expected signature.
            
        Raises:
            MSGraphCryptoError: If signature verification fails.
        """
        expected_signature = base64.b64decode(signature_b64)
        computed_signature = hmac.new(
            symmetric_key,
            encrypted_data,
            "sha256",
        ).digest()

        if not hmac.compare_digest(expected_signature, computed_signature):
            raise MSGraphCryptoError("Data signature verification failed", code="signature_error")

        logger.debug("Notification signature verified successfully")

    def get_env_vars_for_config(self) -> dict[str, str]:
        """Get environment variable values for configuration.
        
        Returns:
            Dictionary with base64-encoded values ready for env vars.
            
        Raises:
            MSGraphCryptoError: If certificate not loaded.
        """
        if not self.is_configured():
            raise MSGraphCryptoError("Certificate not configured", code="not_configured")

        # Get PEM bytes
        private_key_pem = self._private_key.private_bytes(  # type: ignore
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        certificate_pem = self._certificate.public_bytes(serialization.Encoding.PEM)  # type: ignore

        return {
            "MS_GRAPH_PRIVATE_KEY": base64.b64encode(private_key_pem).decode("ascii"),
            "MS_GRAPH_CERTIFICATE": base64.b64encode(certificate_pem).decode("ascii"),
            "MS_GRAPH_CERTIFICATE_ID": self._cert_id,  # type: ignore
        }

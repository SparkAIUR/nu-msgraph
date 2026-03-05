"""Certificate generation utility for Rich Notifications.

This script generates a self-signed certificate for MS Graph
Rich Notifications and outputs the environment variables needed.
"""

import base64

from nu_msgraph import MSGraphCrypto


def main() -> None:
    """Generate certificate and print environment variables."""
    
    crypto = MSGraphCrypto()
    
    # Generate new certificate
    private_key_pem, certificate_pem, cert_id = crypto.generate_certificate(
        common_name="MS Graph Notifications",
        organization="My Organization",
        validity_days=365,
    )
    
    # Encode to base64 for environment variables
    private_key_b64 = base64.b64encode(private_key_pem).decode("ascii")
    certificate_b64 = base64.b64encode(certificate_pem).decode("ascii")
    
    print("=" * 60)
    print("Certificate Generated Successfully!")
    print("=" * 60)
    print()
    print(f"Certificate ID: {cert_id}")
    print()
    print("Add these to your .env file or environment:")
    print()
    print(f"MS_GRAPH_CERTIFICATE_ID={cert_id}")
    print()
    print("MS_GRAPH_PRIVATE_KEY=\\")
    # Print in chunks for readability
    for i in range(0, len(private_key_b64), 76):
        print(private_key_b64[i:i+76])
    print()
    print("MS_GRAPH_CERTIFICATE=\\")
    for i in range(0, len(certificate_b64), 76):
        print(certificate_b64[i:i+76])
    print()
    print("=" * 60)
    print()
    print("⚠️  IMPORTANT: Store the private key securely!")
    print("    Never commit it to version control.")
    print()
    print("The certificate is valid for 365 days.")
    print("After expiration, generate a new one and update your subscriptions.")


def save_to_files(output_dir: str = ".") -> None:
    """Generate certificate and save to files.
    
    Args:
        output_dir: Directory to save files to.
    """
    import os
    
    crypto = MSGraphCrypto()
    
    private_key_pem, certificate_pem, cert_id = crypto.generate_certificate(
        common_name="MS Graph Notifications",
        organization="My Organization",
        validity_days=365,
    )
    
    # Save files
    private_key_path = os.path.join(output_dir, "msgraph_private_key.pem")
    certificate_path = os.path.join(output_dir, "msgraph_certificate.pem")
    
    with open(private_key_path, "wb") as f:
        f.write(private_key_pem)
    
    with open(certificate_path, "wb") as f:
        f.write(certificate_pem)
    
    print(f"Private key saved to: {private_key_path}")
    print(f"Certificate saved to: {certificate_path}")
    print(f"Certificate ID: {cert_id}")
    print()
    print("To use these files, base64 encode them and set environment variables:")
    print(f"  cat {private_key_path} | base64 > private_key.b64")
    print(f"  cat {certificate_path} | base64 > certificate.b64")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--save":
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "."
        save_to_files(output_dir)
    else:
        main()

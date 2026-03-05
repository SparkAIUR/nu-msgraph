"""Quick test script to verify MS Graph credentials."""

import asyncio
from nu_msgraph import MSGraphClient, MSGraphConfig, MSGraphError


async def test_credentials():
    """Test that credentials are valid by getting token."""
    print("=" * 50)
    print("MS Graph Credentials Test")
    print("=" * 50)
    
    config = MSGraphConfig()
    
    print(f"\nConfiguration:")
    print(f"  Tenant ID: {config.tenant_id[:8]}...{config.tenant_id[-4:]}")
    print(f"  Client ID: {config.client_id[:8]}...{config.client_id[-4:]}")
    print(f"  From Address: {config.from_address or '(not set)'}")
    print(f"  Webhook URL: {config.webhook_url or '(not set)'}")
    
    if not config.tenant_id or not config.client_id or not config.client_secret:
        print("\n❌ Missing credentials! Set these environment variables:")
        print("   MS_GRAPH_TENANT_ID")
        print("   MS_GRAPH_CLIENT_ID")
        print("   MS_GRAPH_CLIENT_SECRET")
        return False
    
    client = MSGraphClient(config)
    
    print("\n[1] Testing OAuth2 token acquisition...")
    try:
        token = await client._get_access_token()
        print(f"    ✅ Token acquired: {token[:20]}...{token[-10:]}")
    except MSGraphError as e:
        print(f"    ❌ Failed: {e}")
        return False
    
    if config.from_address:
        print(f"\n[2] Testing user info for {config.from_address}...")
        try:
            user = await client.get_user_info()
            print(f"    ✅ User found:")
            print(f"       Display Name: {user.get('displayName', 'N/A')}")
            print(f"       Mail: {user.get('mail', 'N/A')}")
            print(f"       ID: {user.get('id', 'N/A')}")
        except MSGraphError as e:
            print(f"    ❌ Failed: {e}")
            print("       (This might mean the email doesn't have a mailbox or permissions are missing)")
    else:
        print("\n[2] Skipping user info test (MS_GRAPH_FROM_ADDRESS not set)")
    
    print("\n" + "=" * 50)
    print("✅ Credentials are valid!")
    print("=" * 50)
    return True


async def test_send_email(to_address: str):
    """Test sending an email."""
    print("\n" + "=" * 50)
    print("MS Graph Send Email Test")
    print("=" * 50)
    
    config = MSGraphConfig()
    
    if not config.from_address:
        print("❌ MS_GRAPH_FROM_ADDRESS not set!")
        return False
    
    client = MSGraphClient(config)
    
    print(f"\nSending test email...")
    print(f"  From: {config.from_address}")
    print(f"  To: {to_address}")
    
    try:
        result = await client.send_email(
            to_address=to_address,
            subject="[Test] nu-msgraph library test",
            body_text="This is a test email from nu-msgraph library.",
            body_html="""
            <html>
            <body>
                <h2>Test Email from nu-msgraph</h2>
                <p>If you receive this email, the library is working correctly!</p>
                <hr>
                <p style="color: gray; font-size: 12px;">
                    Sent via nu-msgraph Python library
                </p>
            </body>
            </html>
            """,
        )
        print(f"\n✅ Email sent successfully!")
        print(f"   Request ID: {result['request_id']}")
        return True
    except MSGraphError as e:
        print(f"\n❌ Failed to send email: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "send":
        if len(sys.argv) < 3:
            print("Usage: python test_integration.py send <recipient_email>")
            sys.exit(1)
        asyncio.run(test_send_email(sys.argv[2]))
    else:
        asyncio.run(test_credentials())

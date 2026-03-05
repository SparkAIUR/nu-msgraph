"""Basic email sending example using nu-msgraph."""

import asyncio

from nu_msgraph import MSGraphClient, MSGraphConfig, MSGraphError


async def main() -> None:
    """Send a simple email via Microsoft Graph API."""
    
    # Option 1: Load config from environment variables
    # (MS_GRAPH_TENANT_ID, MS_GRAPH_CLIENT_ID, MS_GRAPH_CLIENT_SECRET, MS_GRAPH_FROM_ADDRESS)
    config = MSGraphConfig()
    
    # Option 2: Provide config explicitly
    # config = MSGraphConfig(
    #     tenant_id="your-tenant-id",
    #     client_id="your-client-id",
    #     client_secret="your-client-secret",
    #     from_address="sender@yourdomain.com",
    # )
    
    # Create client
    client = MSGraphClient(config)
    
    # Check if configured
    if not client.is_enabled:
        print("Error: MS Graph API is not configured.")
        print("Set the following environment variables:")
        print("  - MS_GRAPH_TENANT_ID")
        print("  - MS_GRAPH_CLIENT_ID")
        print("  - MS_GRAPH_CLIENT_SECRET")
        print("  - MS_GRAPH_FROM_ADDRESS")
        return
    
    try:
        # Send a simple text email
        result = await client.send_email(
            to_address="recipient@example.com",
            subject="Hello from nu-msgraph!",
            body_text="This is a test email sent via Microsoft Graph API.",
        )
        
        print(f"Email sent successfully!")
        print(f"  Request ID: {result['request_id']}")
        print(f"  To: {result['to']}")
        print(f"  Subject: {result['subject']}")
        
    except MSGraphError as e:
        print(f"Failed to send email: {e}")
        print(f"  Error code: {e.code}")
        if e.status_code:
            print(f"  HTTP status: {e.status_code}")


async def send_html_email() -> None:
    """Send an HTML email with CC and BCC recipients."""
    
    config = MSGraphConfig()
    client = MSGraphClient(config)
    
    try:
        result = await client.send_email(
            to_address="recipient@example.com",
            subject="Monthly Newsletter",
            body_text="Please view this email in an HTML-capable client.",
            body_html="""
            <html>
            <body>
                <h1>Monthly Newsletter</h1>
                <p>Hello,</p>
                <p>This is our <strong>monthly newsletter</strong> with important updates.</p>
                <ul>
                    <li>Feature 1: Amazing new capability</li>
                    <li>Feature 2: Performance improvements</li>
                    <li>Feature 3: Bug fixes</li>
                </ul>
                <p>Best regards,<br>The Team</p>
            </body>
            </html>
            """,
            cc_addresses=["cc1@example.com", "cc2@example.com"],
            bcc_addresses=["bcc@example.com"],
            reply_to_address="reply@example.com",
            importance="high",
        )
        
        print(f"HTML email sent! Request ID: {result['request_id']}")
        
    except MSGraphError as e:
        print(f"Failed to send email: {e}")


async def list_inbox_messages() -> None:
    """List recent messages from inbox."""
    
    config = MSGraphConfig()
    client = MSGraphClient(config)
    
    try:
        messages = await client.list_messages(
            folder="inbox",
            top=5,
            select=["id", "subject", "from", "receivedDateTime", "isRead"],
        )
        
        print(f"Found {len(messages)} messages in inbox:\n")
        
        for msg in messages:
            subject = msg.get("subject", "(no subject)")
            from_email = (
                msg.get("from", {})
                .get("emailAddress", {})
                .get("address", "unknown")
            )
            received = msg.get("receivedDateTime", "")
            is_read = "Read" if msg.get("isRead") else "Unread"
            
            print(f"  [{is_read}] {subject}")
            print(f"    From: {from_email}")
            print(f"    Received: {received}")
            print()
            
    except MSGraphError as e:
        print(f"Failed to list messages: {e}")


if __name__ == "__main__":
    asyncio.run(main())

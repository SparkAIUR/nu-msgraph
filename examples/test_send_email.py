#!/usr/bin/env python3
"""Test sending an email via MS Graph."""

import asyncio
from nu_msgraph import MSGraphClient, MSGraphConfig


async def send_test():
    config = MSGraphConfig()
    
    print("=" * 50)
    print("MS Graph Email Send Test")
    print("=" * 50)
    print(f"From: {config.from_address}")
    print(f"To: {config.from_address} (self)")
    print()
    
    client = MSGraphClient(config)
    
    print("Sending test email...")
    result = await client.send_email(
        to_address=config.from_address,  # Send to self to trigger webhook
        subject="[TEST] nu-msgraph Webhook Test",
        body_html="<h1>Webhook Test</h1><p>This email should trigger a webhook notification!</p>",
        body_text="Webhook Test - This email should trigger a webhook notification!",
    )
    print()
    print("✅ Email sent successfully!")
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(send_test())

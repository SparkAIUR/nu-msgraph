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
    print(f"To: jsavage@flipcofinancial.com")
    print()
    
    client = MSGraphClient(config)
    
    print("Sending test email...")
    result = await client.send_email(
        to_address="jsavage@flipcofinancial.com",
        subject="[TEST] nu-msgraph Library Test",
        body_html="<h1>Hello!</h1><p>This is a test email from the <b>nu-msgraph</b> library.</p><p>If you received this, the integration is working correctly!</p>",
        body_text="Hello! This is a test email from the nu-msgraph library.",
    )
    print()
    print("✅ Email sent successfully!")
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(send_test())

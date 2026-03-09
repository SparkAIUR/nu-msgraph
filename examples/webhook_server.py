#!/usr/bin/env python3
"""Local webhook server for testing MS Graph subscriptions.

Usage:
    1. Start this server: uv run python examples/webhook_server.py
    2. In another terminal: ngrok http 8000
    3. Copy the ngrok HTTPS URL
    4. Run subscription test: MS_GRAPH_WEBHOOK_URL=https://xxx.ngrok.io/webhook uv run python examples/test_subscription.py
"""

import asyncio
import json
import os
import uvicorn
from fastapi import FastAPI, Request, Response
from nu_msgraph import (
    MSGraphConfig,
    MSGraphCrypto,
    BaseWebhookHandler,
    ChangeNotification,
    WebhookResponse,
)

app = FastAPI(title="MS Graph Webhook Test Server")

# Initialize crypto for rich notifications (optional)
crypto = MSGraphCrypto()


class TestWebhookHandler(BaseWebhookHandler):
    """Test handler that prints all notifications."""

    async def on_email_created(self, notification: ChangeNotification) -> None:
        print("\n" + "=" * 60)
        print("📧 NEW EMAIL RECEIVED!")
        print("=" * 60)
        print(f"  Resource: {notification.resource}")
        print(f"  Change Type: {notification.change_type}")
        print(f"  Message ID: {notification.message_id}")
        
        if notification.is_rich_notification and notification.encrypted_content:
            print("  📦 Rich Notification - Encrypted content available")
            # Decrypt if crypto is configured
            if crypto._private_key:
                try:
                    decrypted = crypto.decrypt_notification(notification.encrypted_content)
                    print(f"  Decrypted content: {json.dumps(decrypted, indent=2)}")
                except Exception as e:
                    print(f"  Decryption failed: {e}")
        print("=" * 60 + "\n")

    async def on_email_updated(self, notification: ChangeNotification) -> None:
        print(f"📝 EMAIL UPDATED: {notification.resource}")

    async def on_email_deleted(self, notification: ChangeNotification) -> None:
        print(f"🗑️ EMAIL DELETED: {notification.resource}")


handler = TestWebhookHandler()


@app.get("/")
async def root():
    return {"status": "running", "message": "MS Graph Webhook Test Server"}


@app.api_route("/webhook", methods=["GET", "POST"])
async def webhook(request: Request):
    """Handle MS Graph webhook notifications."""
    
    # Check for validation token (subscription creation)
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        print(f"✅ Received validation request, token: {validation_token[:20]}...")
        return Response(content=validation_token, media_type="text/plain")
    
    # Process notification
    try:
        body = await request.json()
        print(f"\n📨 Received webhook payload: {json.dumps(body, indent=2)[:500]}...")
        
        # Process the notification
        response = await handler.process_request(body)
        
        if response.status_code == 200:
            print("✅ Notification processed successfully")
        else:
            print(f"✅ Response: {response.status_code}")
            
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.media_type,
        )
        
    except Exception as e:
        print(f"❌ Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        return Response(content="Error", status_code=500)


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    print("=" * 60)
    print("MS Graph Webhook Test Server")
    print("=" * 60)
    print()
    print("Server starting on http://localhost:8000")
    print()
    print("Next steps:")
    print("  1. In another terminal, run: ngrok http 8000")
    print("  2. Copy the ngrok HTTPS URL (e.g., https://abc123.ngrok.io)")
    print("  3. Create a subscription using that URL + /webhook")
    print()
    print("Endpoints:")
    print("  GET  /          - Status check")
    print("  GET  /health    - Health check")
    print("  POST /webhook   - MS Graph notifications")
    print("=" * 60)
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

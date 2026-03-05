"""FastAPI webhook integration example.

This example shows how to integrate nu-msgraph webhook handling
with a FastAPI application.

Run with: uvicorn webhook_fastapi:app --reload
"""

from typing import Any

from fastapi import FastAPI, Request, Response, HTTPException, status
from pydantic import BaseModel

from nu_msgraph import (
    BaseWebhookHandler,
    ChangeNotification,
    MSGraphClient,
    MSGraphConfig,
    MSGraphCrypto,
    MSGraphSubscriptionService,
)


# ============================================================================
# Configuration
# ============================================================================

# Load config from environment
config = MSGraphConfig()

# Initialize crypto for Rich Notifications (optional)
crypto = MSGraphCrypto.from_config(config)

# Initialize client and services
client = MSGraphClient(config)
subscription_service = MSGraphSubscriptionService(client, config, crypto=crypto)


# ============================================================================
# Custom Webhook Handler
# ============================================================================

class MyWebhookHandler(BaseWebhookHandler):
    """Custom webhook handler for your application.
    
    Implement your business logic in these methods.
    """
    
    async def on_email_created(self, notification: ChangeNotification) -> None:
        """Handle new email notifications.
        
        This is called when a new email arrives in the monitored mailbox.
        """
        print(f"📧 New email received!")
        print(f"   Message ID: {notification.message_id}")
        print(f"   Subscription: {notification.subscription_id}")
        
        # If Rich Notifications are enabled, we have the full email content
        if notification.decrypted_content:
            email_data = notification.decrypted_content
            subject = email_data.get("subject", "(no subject)")
            sender = (
                email_data.get("from", {})
                .get("emailAddress", {})
                .get("address", "unknown")
            )
            body_preview = email_data.get("bodyPreview", "")[:100]
            
            print(f"   Subject: {subject}")
            print(f"   From: {sender}")
            print(f"   Preview: {body_preview}...")
            
            # Example: Process the email
            # await self.process_incoming_email(email_data)
        else:
            # Basic notification - need to fetch email content if needed
            print("   (Basic notification - fetch email for details)")
            
            # Example: Fetch the email
            # if notification.message_id:
            #     email = await client.get_message(notification.message_id)
            #     await self.process_incoming_email(email)
    
    async def on_email_updated(self, notification: ChangeNotification) -> None:
        """Handle email update notifications.
        
        This is called when an email is modified (e.g., marked as read).
        """
        print(f"📝 Email updated!")
        print(f"   Message ID: {notification.message_id}")
        
        if notification.decrypted_content:
            is_read = notification.decrypted_content.get("isRead", False)
            print(f"   Is Read: {is_read}")
    
    async def on_email_deleted(self, notification: ChangeNotification) -> None:
        """Handle email deletion notifications."""
        print(f"🗑️ Email deleted!")
        print(f"   Message ID: {notification.message_id}")


# Create handler instance
webhook_handler = MyWebhookHandler(config=config, crypto=crypto)


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="MS Graph Webhook Example",
    description="Example FastAPI application with MS Graph webhook integration",
)


@app.post("/webhook/notifications")
async def receive_notifications(request: Request) -> Response:
    """Receive Microsoft Graph change notifications.
    
    This endpoint handles:
    1. Validation requests during subscription setup
    2. Notification payloads when emails arrive/change
    """
    result = await webhook_handler.process_request(request)
    
    return Response(
        content=result.content,
        status_code=result.status_code,
        media_type=result.media_type,
    )


# ============================================================================
# Subscription Management Endpoints (Optional)
# ============================================================================

class CreateSubscriptionRequest(BaseModel):
    """Request to create a new subscription."""
    user_email: str | None = None
    change_types: list[str] = ["created"]
    include_resource_data: bool = False


class SubscriptionResponse(BaseModel):
    """Subscription response."""
    subscription_id: str
    resource: str
    expiration_datetime: str
    notification_url: str


@app.post("/api/subscriptions", response_model=SubscriptionResponse)
async def create_subscription(request: CreateSubscriptionRequest) -> dict[str, Any]:
    """Create a new webhook subscription."""
    try:
        result = await subscription_service.create_subscription(
            user_email=request.user_email,
            change_types=request.change_types,
            include_resource_data=request.include_resource_data,
        )
        return {
            "subscription_id": result["subscription_id"],
            "resource": result["resource"],
            "expiration_datetime": result["expiration_datetime"],
            "notification_url": result["notification_url"],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.get("/api/subscriptions")
async def list_subscriptions() -> dict[str, Any]:
    """List all active subscriptions."""
    try:
        subscriptions = await subscription_service.list_subscriptions()
        return {
            "subscriptions": subscriptions,
            "count": len(subscriptions),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.delete("/api/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str) -> dict[str, str]:
    """Delete a subscription."""
    try:
        await subscription_service.delete_subscription(subscription_id)
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "ms_graph_configured": config.is_configured(),
        "crypto_configured": crypto.is_configured() if crypto else False,
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

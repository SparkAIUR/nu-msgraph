#!/usr/bin/env python3
"""Test creating a subscription to monitor emails.

Prerequisites:
    1. Start webhook server: uv run python examples/webhook_server.py
    2. Start ngrok: ngrok http 8000
    3. Set environment variables:
       - MS_GRAPH_WEBHOOK_URL=https://your-ngrok-url.ngrok.io/webhook
       - MS_GRAPH_CLIENT_ID, MS_GRAPH_CLIENT_SECRET, MS_GRAPH_TENANT_ID, MS_GRAPH_FROM_ADDRESS

Usage:
    python examples/test_subscription.py create   # Create a subscription
    python examples/test_subscription.py list     # List subscriptions
    python examples/test_subscription.py delete   # Delete all subscriptions
"""

import asyncio
import sys
from nu_msgraph import MSGraphConfig, MSGraphClient, MSGraphSubscriptionService


async def create_subscription():
    """Create a new subscription."""
    config = MSGraphConfig()
    client = MSGraphClient(config)
    
    print("=" * 60)
    print("Creating MS Graph Subscription")
    print("=" * 60)
    print(f"Mailbox: {config.from_address}")
    print(f"Webhook URL: {config.webhook_url}")
    print()
    
    if not config.webhook_url:
        print("❌ Error: MS_GRAPH_WEBHOOK_URL not set")
        print("   Run ngrok and set the URL first:")
        print("   export MS_GRAPH_WEBHOOK_URL=https://xxx.ngrok.io/webhook")
        return
    
    service = MSGraphSubscriptionService(client)
    
    try:
        subscription = await service.create_subscription(
            user_email=config.from_address,
            webhook_url=config.webhook_url,
            expiration_hours=1,  # 1 hour for testing
            change_types=["created"],
        )
        
        print("✅ Subscription created successfully!")
        print()
        print(f"  ID: {subscription['subscription_id']}")
        print(f"  Resource: {subscription['resource']}")
        print(f"  Change Types: {subscription['change_type']}")
        print(f"  Expiration: {subscription['expiration_datetime']}")
        print()
        print("Now send an email to", config.from_address, "to test the webhook!")
        
    except Exception as e:
        print(f"❌ Failed to create subscription: {e}")


async def list_subscriptions():
    """List all subscriptions."""
    config = MSGraphConfig()
    client = MSGraphClient(config)
    service = MSGraphSubscriptionService(client)
    
    print("=" * 60)
    print("Listing MS Graph Subscriptions")
    print("=" * 60)
    print()
    
    try:
        subscriptions = await service.list_subscriptions()
        
        if not subscriptions:
            print("No active subscriptions found.")
            return
            
        for sub in subscriptions:
            print(f"ID: {sub['id']}")
            print(f"  Resource: {sub['resource']}")
            print(f"  Change Types: {sub['changeType']}")
            print(f"  Expiration: {sub['expirationDateTime']}")
            print(f"  Notification URL: {sub.get('notificationUrl', 'N/A')}")
            print()
            
    except Exception as e:
        print(f"❌ Failed to list subscriptions: {e}")


async def delete_all_subscriptions():
    """Delete all subscriptions."""
    config = MSGraphConfig()
    client = MSGraphClient(config)
    service = MSGraphSubscriptionService(client)
    
    print("=" * 60)
    print("Deleting All MS Graph Subscriptions")
    print("=" * 60)
    print()
    
    try:
        subscriptions = await service.list_subscriptions()
        
        if not subscriptions:
            print("No subscriptions to delete.")
            return
            
        for sub in subscriptions:
            sub_id = sub['id']
            print(f"Deleting subscription {sub_id}...")
            await service.delete_subscription(sub_id)
            print(f"  ✅ Deleted")
            
        print()
        print("All subscriptions deleted.")
            
    except Exception as e:
        print(f"❌ Failed to delete subscriptions: {e}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python test_subscription.py <command>")
        print()
        print("Commands:")
        print("  create  - Create a new subscription")
        print("  list    - List all subscriptions")
        print("  delete  - Delete all subscriptions")
        return
    
    command = sys.argv[1].lower()
    
    if command == "create":
        await create_subscription()
    elif command == "list":
        await list_subscriptions()
    elif command == "delete":
        await delete_all_subscriptions()
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    asyncio.run(main())

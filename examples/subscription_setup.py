"""Webhook subscription setup example."""

import asyncio

from nu_msgraph import (
    MSGraphClient,
    MSGraphConfig,
    MSGraphCrypto,
    MSGraphError,
    MSGraphSubscriptionService,
)


async def create_basic_subscription() -> None:
    """Create a basic webhook subscription for new emails."""
    
    config = MSGraphConfig()
    client = MSGraphClient(config)
    subscription_service = MSGraphSubscriptionService(client, config)
    
    if not config.webhook_url:
        print("Error: MS_GRAPH_WEBHOOK_URL environment variable not set.")
        print("Set it to your public HTTPS endpoint, e.g.:")
        print("  export MS_GRAPH_WEBHOOK_URL=https://your-server.com/webhook/notifications")
        return
    
    try:
        # Create subscription for new emails only
        result = await subscription_service.create_subscription(
            change_types=["created"],
            expiration_hours=72,  # Max 72 hours
        )
        
        print("Subscription created successfully!")
        print(f"  Subscription ID: {result['subscription_id']}")
        print(f"  Resource: {result['resource']}")
        print(f"  Notification URL: {result['notification_url']}")
        print(f"  Expires: {result['expiration_datetime']}")
        print(f"  Client State: {result['client_state']}")
        
        print("\n⚠️  Important: Save the subscription ID and client state!")
        print("    You'll need them for renewal and validation.")
        
    except MSGraphError as e:
        print(f"Failed to create subscription: {e}")


async def create_rich_notification_subscription() -> None:
    """Create a subscription with Rich Notifications (encrypted content)."""
    
    config = MSGraphConfig()
    client = MSGraphClient(config)
    
    # Initialize crypto service
    crypto = MSGraphCrypto.from_config(config)
    
    if not crypto.is_configured():
        print("Rich Notifications require certificate configuration.")
        print("Generate a certificate first:")
        print("  python -c 'from examples.generate_certificate import main; main()'")
        return
    
    subscription_service = MSGraphSubscriptionService(client, config, crypto=crypto)
    
    try:
        result = await subscription_service.create_subscription(
            change_types=["created", "updated"],
            expiration_hours=72,
            include_resource_data=True,  # Enable Rich Notifications
        )
        
        print("Rich Notification subscription created!")
        print(f"  Subscription ID: {result['subscription_id']}")
        print(f"  Include Resource Data: {result['include_resource_data']}")
        print(f"  Expires: {result['expiration_datetime']}")
        
    except MSGraphError as e:
        print(f"Failed to create subscription: {e}")


async def list_subscriptions() -> None:
    """List all active subscriptions."""
    
    config = MSGraphConfig()
    client = MSGraphClient(config)
    subscription_service = MSGraphSubscriptionService(client, config)
    
    try:
        subscriptions = await subscription_service.list_subscriptions()
        
        if not subscriptions:
            print("No active subscriptions found.")
            return
        
        print(f"Found {len(subscriptions)} active subscription(s):\n")
        
        for sub in subscriptions:
            print(f"  ID: {sub.get('id')}")
            print(f"  Resource: {sub.get('resource')}")
            print(f"  Change Type: {sub.get('changeType')}")
            print(f"  Notification URL: {sub.get('notificationUrl')}")
            print(f"  Expires: {sub.get('expirationDateTime')}")
            
            # Check if needs renewal
            if subscription_service.needs_renewal(sub.get('expirationDateTime', '')):
                print("  ⚠️  NEEDS RENEWAL")
            print()
            
    except MSGraphError as e:
        print(f"Failed to list subscriptions: {e}")


async def renew_subscription(subscription_id: str) -> None:
    """Renew an existing subscription."""
    
    config = MSGraphConfig()
    client = MSGraphClient(config)
    subscription_service = MSGraphSubscriptionService(client, config)
    
    try:
        result = await subscription_service.renew_subscription(
            subscription_id=subscription_id,
            expiration_hours=72,
        )
        
        print(f"Subscription renewed!")
        print(f"  New expiration: {result['expiration_datetime']}")
        
    except MSGraphError as e:
        print(f"Failed to renew subscription: {e}")


async def delete_subscription(subscription_id: str) -> None:
    """Delete a subscription."""
    
    config = MSGraphConfig()
    client = MSGraphClient(config)
    subscription_service = MSGraphSubscriptionService(client, config)
    
    try:
        await subscription_service.delete_subscription(subscription_id)
        print(f"Subscription {subscription_id} deleted successfully.")
        
    except MSGraphError as e:
        print(f"Failed to delete subscription: {e}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python subscription_setup.py create        - Create basic subscription")
        print("  python subscription_setup.py create-rich   - Create Rich Notification subscription")
        print("  python subscription_setup.py list          - List all subscriptions")
        print("  python subscription_setup.py renew <id>    - Renew subscription")
        print("  python subscription_setup.py delete <id>   - Delete subscription")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "create":
        asyncio.run(create_basic_subscription())
    elif command == "create-rich":
        asyncio.run(create_rich_notification_subscription())
    elif command == "list":
        asyncio.run(list_subscriptions())
    elif command == "renew":
        if len(sys.argv) < 3:
            print("Error: subscription ID required")
            sys.exit(1)
        asyncio.run(renew_subscription(sys.argv[2]))
    elif command == "delete":
        if len(sys.argv) < 3:
            print("Error: subscription ID required")
            sys.exit(1)
        asyncio.run(delete_subscription(sys.argv[2]))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

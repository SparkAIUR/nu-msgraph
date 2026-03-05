# nu-msgraph

Microsoft Graph API client for Python with email operations, webhook subscriptions, and Rich Notifications support.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- 🔐 **OAuth2 Client Credentials** - Automatic token management with caching and refresh
- 📧 **Email Operations** - Send, list, and retrieve emails via Graph API
- 🔔 **Webhook Subscriptions** - Create, renew, and manage change notification subscriptions
- 🔒 **Rich Notifications** - Full support for encrypted webhook payloads with certificate management
- 🚀 **Framework Agnostic** - Works with FastAPI, Flask, Django, or standalone
- ⚡ **Async First** - Built on `httpx` for high-performance async operations
- 📦 **Type Safe** - Full type annotations with Pydantic models

## Installation

```bash
# From PyPI (when published)
pip install nu-msgraph

# From Git
pip install git+https://github.com/AI-Hivemind/nu-msgraph.git

# With FastAPI integration
pip install "nu-msgraph[fastapi]"

# For development
pip install "nu-msgraph[dev]"
```

## Quick Start

### Send an Email

```python
import asyncio
from nu_msgraph import MSGraphClient, MSGraphConfig

async def main():
    config = MSGraphConfig(
        tenant_id="your-tenant-id",
        client_id="your-client-id",
        client_secret="your-client-secret",
        from_address="sender@yourdomain.com",
    )
    
    client = MSGraphClient(config)
    
    result = await client.send_email(
        to_address="recipient@example.com",
        subject="Hello from nu-msgraph!",
        body_text="This is a test email.",
        body_html="<h1>This is a test email.</h1>",
    )
    
    print(f"Email sent! Request ID: {result['request_id']}")

asyncio.run(main())
```

### Create a Webhook Subscription

```python
import asyncio
from nu_msgraph import MSGraphClient, MSGraphSubscriptionService, MSGraphConfig

async def main():
    config = MSGraphConfig(
        tenant_id="your-tenant-id",
        client_id="your-client-id",
        client_secret="your-client-secret",
        from_address="mailbox@yourdomain.com",
        webhook_url="https://your-server.com/webhook/notifications",
    )
    
    client = MSGraphClient(config)
    subscription_service = MSGraphSubscriptionService(client, config)
    
    # Create subscription for new emails
    result = await subscription_service.create_subscription(
        change_types=["created"],
        expiration_hours=72,  # Max 72 hours
    )
    
    print(f"Subscription created: {result['subscription_id']}")
    print(f"Expires: {result['expiration_datetime']}")

asyncio.run(main())
```

### Handle Webhook Notifications

```python
from nu_msgraph import BaseWebhookHandler, ChangeNotification

class MyWebhookHandler(BaseWebhookHandler):
    async def on_email_created(self, notification: ChangeNotification) -> None:
        print(f"New email received: {notification.message_id}")
        
        # If Rich Notifications enabled, you have the full email content
        if notification.decrypted_content:
            email = notification.decrypted_content
            print(f"Subject: {email.get('subject')}")
            print(f"From: {email.get('from', {}).get('emailAddress', {}).get('address')}")
    
    async def on_email_updated(self, notification: ChangeNotification) -> None:
        print(f"Email updated: {notification.message_id}")
    
    async def on_email_deleted(self, notification: ChangeNotification) -> None:
        print(f"Email deleted: {notification.message_id}")

# FastAPI Integration
from fastapi import FastAPI, Request, Response
from nu_msgraph import MSGraphConfig, MSGraphCrypto

app = FastAPI()
config = MSGraphConfig(...)
crypto = MSGraphCrypto()  # Load from env for Rich Notifications
handler = MyWebhookHandler(config=config, crypto=crypto)

@app.post("/webhook/notifications")
async def webhook(request: Request) -> Response:
    return await handler.process_request(request)
```

### Rich Notifications Setup

Generate a certificate for encrypted notifications:

```python
from nu_msgraph import MSGraphCrypto

crypto = MSGraphCrypto()

# Generate new certificate
private_key_pem, certificate_pem, cert_id = crypto.generate_certificate(
    common_name="My App MS Graph Notifications",
    validity_days=365,
)

# Save these securely - you'll need them for webhook decryption
print(f"Certificate ID: {cert_id}")
print("Set these environment variables:")
print("  MS_GRAPH_PRIVATE_KEY=<base64-encoded private key>")
print("  MS_GRAPH_CERTIFICATE=<base64-encoded certificate>")
print(f"  MS_GRAPH_CERTIFICATE_ID={cert_id}")
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `MS_GRAPH_TENANT_ID` | Azure AD Tenant ID | Yes |
| `MS_GRAPH_CLIENT_ID` | Application (client) ID | Yes |
| `MS_GRAPH_CLIENT_SECRET` | Client secret | Yes |
| `MS_GRAPH_FROM_ADDRESS` | Sender email address | Yes |
| `MS_GRAPH_WEBHOOK_URL` | Public HTTPS URL for webhooks | For subscriptions |
| `MS_GRAPH_PRIVATE_KEY` | Base64-encoded private key PEM | For Rich Notifications |
| `MS_GRAPH_CERTIFICATE` | Base64-encoded certificate PEM | For Rich Notifications |
| `MS_GRAPH_CERTIFICATE_ID` | Certificate ID | For Rich Notifications |

### Using Pydantic Settings

```python
from nu_msgraph import MSGraphConfig

# Automatically loads from environment variables
config = MSGraphConfig()

# Or provide values directly
config = MSGraphConfig(
    tenant_id="...",
    client_id="...",
    client_secret="...",
    from_address="...",
)
```

## API Reference

### MSGraphClient

The main client for Microsoft Graph API operations.

```python
client = MSGraphClient(config)

# Send email
await client.send_email(to_address="...", subject="...", body_text="...")

# List messages
messages = await client.list_messages(folder="inbox", top=10)

# Get specific message
message = await client.get_message(message_id="...")

# Get user info
user = await client.get_user_info()
```

### MSGraphSubscriptionService

Manage webhook subscriptions.

```python
service = MSGraphSubscriptionService(client, config)

# Create subscription
await service.create_subscription(change_types=["created"], expiration_hours=72)

# Renew subscription
await service.renew_subscription(subscription_id="...")

# List subscriptions
subscriptions = await service.list_subscriptions()

# Delete subscription
await service.delete_subscription(subscription_id="...")
```

### MSGraphCrypto

Handle Rich Notifications encryption.

```python
crypto = MSGraphCrypto()

# Generate certificate
private_key, cert, cert_id = crypto.generate_certificate()

# Load from files
crypto.load_certificate(private_key_pem, certificate_pem, cert_id)

# Load from environment
crypto.load_from_env()

# Decrypt notification
decrypted = crypto.decrypt_notification(encrypted_content)
```

## Development

```bash
# Clone the repository
git clone https://github.com/AI-Hivemind/nu-msgraph.git
cd nu-msgraph

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=nu_msgraph --cov-report=html

# Format code
black src tests
ruff check --fix src tests

# Type checking
mypy src
```

## License

MIT License - see [LICENSE](LICENSE) for details.

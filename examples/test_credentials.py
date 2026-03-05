#!/usr/bin/env python3
"""Simple credential test - directly tests OAuth2 token acquisition."""

import asyncio
import os
import httpx


async def test_credentials():
    """Test MS Graph credentials by acquiring an OAuth2 token."""
    tenant_id = os.environ.get("MS_GRAPH_TENANT_ID")
    client_id = os.environ.get("MS_GRAPH_CLIENT_ID")
    client_secret = os.environ.get("MS_GRAPH_CLIENT_SECRET")

    print("=" * 50)
    print("MS Graph Credential Test")
    print("=" * 50)
    print()
    print(f"Tenant ID: {tenant_id[:8]}...{tenant_id[-4:]}")
    print(f"Client ID: {client_id[:8]}...{client_id[-4:]}")
    print(f"Secret:    {client_secret[:4]}...")
    print()

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    print(f"[1] Requesting token from: {token_url}")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )
        
        print(f"    Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            token_type = data.get("token_type")
            expires_in = data.get("expires_in")
            access_token = data.get("access_token", "")
            
            print()
            print("    ✅ Token acquired successfully!")
            print(f"    Token type: {token_type}")
            print(f"    Expires in: {expires_in} seconds")
            print(f"    Token preview: {access_token[:50]}...")
            
            # Test the token by calling /me endpoint
            print()
            print("[2] Testing token with /me endpoint...")
            
            headers = {"Authorization": f"Bearer {access_token}"}
            me_response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=headers,
            )
            
            print(f"    Response status: {me_response.status_code}")
            
            if me_response.status_code == 200:
                me_data = me_response.json()
                print(f"    Display Name: {me_data.get('displayName')}")
                print(f"    Email: {me_data.get('mail')}")
            else:
                # /me won't work with app-only auth, but we can try /organization
                print("    (Note: /me requires delegated auth, trying /organization...)")
                
                org_response = await client.get(
                    "https://graph.microsoft.com/v1.0/organization",
                    headers=headers,
                )
                
                print(f"    /organization status: {org_response.status_code}")
                
                if org_response.status_code == 200:
                    org_data = org_response.json()
                    orgs = org_data.get("value", [])
                    if orgs:
                        print(f"    ✅ Organization: {orgs[0].get('displayName')}")
                else:
                    print(f"    Response: {org_response.text}")
            
            print()
            print("=" * 50)
            print("✅ CREDENTIALS ARE VALID!")
            print("=" * 50)
            
        else:
            print()
            print("    ❌ Failed to acquire token!")
            print(f"    Error: {response.text}")
            print()
            print("=" * 50)
            print("❌ CREDENTIALS ARE INVALID")
            print("=" * 50)


if __name__ == "__main__":
    asyncio.run(test_credentials())

"""Debug test to show exact request/response."""

import httpx
import asyncio
from typing import Optional


async def debug_test(api_key: str, api_base: str, model: str) -> tuple[bool, str]:
    """Debug test shows exact request and response."""
    
    print(f"=== DEBUG TEST ===")
    print(f"API Base: {api_base}")
    print(f"Model: {model}")
    print(f"Key: {api_key[:10]}...")
    
    base = api_base.rstrip('/')
    
    # Try the most common endpoint
    endpoint = "/v1/chat/completions"
    url = f"{base}{endpoint}"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5
    }
    
    print(f"\nRequest:")
    print(f"URL: {url}")
    print(f"Headers: {headers}")
    print(f"Payload: {payload}")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            print(f"\nResponse:")
            print(f"Status: {response.status_code}")
            print(f"Headers: {dict(response.headers)}")
            print(f"Body: {response.text}")
            
            if response.status_code == 200:
                return True, "Connected!"
            else:
                return False, f"Status {response.status_code}: {response.text[:100]}"
                
    except Exception as e:
        print(f"\nException: {e}")
        return False, f"Exception: {str(e)}"


def debug_test_sync(api_key: str, api_base: str, model: str) -> tuple[bool, str]:
    """Sync wrapper."""
    return asyncio.run(debug_test(api_key, api_base, model))


# Test directly: python -c "from src.utils.test_debug import debug_test_sync; print(debug_test_sync('YOUR_KEY', 'https://api.minimax.chat', 'abab6.5s-chat'))"
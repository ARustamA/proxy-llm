"""Simplified, universal test for any LLM API."""

import httpx
import asyncio
from typing import Optional


async def universal_test(api_key: str, api_base: Optional[str] = None, 
                         model: Optional[str] = None) -> tuple[bool, str]:
    """Universal test tries many LLM API formats and gives detailed feedback."""
    
    if not api_base:
        return False, "No API base URL provided"
    
    base = api_base.rstrip('/')
    clean_key = api_key.strip()
    
    # Common headers combinations to try
    header_sets = [
        {"Authorization": f"Bearer {clean_key}", "Content-Type": "application/json"},
        {"Authorization": clean_key, "Content-Type": "application/json"},
        {"x-api-key": clean_key, "Content-Type": "application/json"},
    ]
    
    # Typical OpenAI-format endpoints
    endpoints_to_try = [
        "/v1/chat/completions",
        "/v1/completions", 
        "/chat/completions",
    ]
    
    # Guess models if none
    models_to_try = [model] if model else [
        "gpt-3.5-turbo", "gpt-4", "default", "chatgpt", 
    ]
    
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for headers in header_sets:
            for endpoint in endpoints_to_try:
                for curr_model in models_to_try:
                    try:
                        response = await client.post(
                            f"{base}{endpoint}",
                            headers=headers,
                            json={
                                "model": curr_model,
                                "messages": [{"role": "user", "content": "Hi"}],
                                "max_tokens": 3
                            }
                        )
                        
                        # Success
                        if response.status_code in (200, 201):
                            return True, f"✓ Works! Model: {curr_model}"
                        
                        # Show what happened
                        msg = ""
                        if response.text:
                            try:
                                j = response.json()
                                msg = j.get("error", {}).get("message", j.get("msg", j.get("message", "")))
                            except:
                                msg = response.text[:60]
                        
                        # This is important - actual model invalidity should trigger next iteration
                        if "not found" in msg.lower() or "invalid" in msg.lower():
                            continue  # trying further models
                        
                        # Different error, and it's likely we can show it now
                        return False, f"Status {response.status_code}: {msg[:100]}"
                        
                    except httpx.TimeoutException:
                        continue
                    except httpx.ConnectError as e:
                        return False, f"Cannot connect to server: {str(e)[:60]}"
                    except Exception as e:
                        continue
    
    # Nothing worked
    return False, "No working endpoints found. Check URL/API key."


def test_api_simple(api_key: str, api_base: Optional[str], 
                   model: Optional[str] = None) -> tuple[bool, str]:
    """Sync wrapper."""
    return asyncio.run(universal_test(api_key, api_base, model))


# For direct testing in script: python -c "from src.utils.test_minimax import test_api_simple; print(test_api_simple('YOUR_KEY', 'https://api.minimax.chat', 'abab6.5s-chat'))"
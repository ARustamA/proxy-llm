"""Enhanced provider test with better diagnostics."""

import httpx
import asyncio
from typing import Optional


async def test_minimax_detailed(api_key: str, api_base: Optional[str] = None, 
                             model: Optional[str] = None) -> tuple[bool, str]:
    """Detailed test for Minimax API."""
    base = api_base or "https://api.minimax.chat"
    
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Try various endpoints
        test_endpoints = [
            "/v1/text/chatcompletion_v2",    # Original
            "/v1/text/chatcompletion_v1",    # Alternative 
            "/v1/text/chatcompletion_pro",    # Pro version?
            "/v1/text/chatcompletion",      # Generic  
        ]
        
        # If no model specified, common ones
        test_models = [model] if model else [
            "abab6.5s-chat", 
            "abab6.5-chat", 
            "abab5.5-chat",
            "abab5-chat", 
            "Mixvoice-o1", 
            "mixlang-x1", 
            "default",
            "airopro",
        ]
        
        for endpoint in test_endpoints:
            for m in test_models:
                try:
                    response = await client.post(
                        base + endpoint,
                        headers=headers,
                        json={
                            "model": m, 
                            "messages": [{"role": "user", "content": "Hi"}],
                            "max_tokens": 8
                        }
                    )
                    
                    if response.status_code == 200:
                        return True, f"Connected! Endpoint: {endpoint}, Model: {m}"
                    elif response.status_code < 500:
                        # Non-server error, might mean endpoint exists but other issue
                        err_detail = ""
                        try:
                            err_detail = response.json().get("error", {}).get("message", 
                                          response.json().get("msg", ""))
                        except:
                            pass
                        
                        if "not found" in err_detail.lower() or "invalid" in err_detail.lower():
                            continue  # Try next
                            
                        return False, f"Error {response.status_code}: {err_detail[:80]}" 
                        
                except httpx.TimeoutException:
                    continue
                except Exception as e:
                    continue
        
        return False, "Could not find working endpoint. Verify API + Model."


async def test_deepseek_detailed(api_key: str, api_base: Optional[str] = None, 
                              model: Optional[str] = None) -> tuple[bool, str]:
    """Detailed test for DeepSeek."""
    base = api_base or "https://api.deepseek.com"
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Try chat completions directly with sample model
        test_model = model or "deepseek-chat"
        
        response = await client.post(
            f"{base}/v1/chat/completions",
            headers=headers,
            json={
                "model": test_model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5
            }
        )
        
        if response.status_code == 200:
            return True, "Connected!"
        elif response.status_code == 404:
            # Maybe wrong endpoint version
            # Try without version
            response2 = await client.post(
                f"{base}/chat/completions",
                headers=headers,
                json={"model": test_model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
            )
            if response2.status_code == 200:
                return True, "Connected (alt endpoint)!";
        
        return False, f"Error {response.status_code}: {response.text[:100]}" 


# Keep original tester but enhance test_provider  
from src.utils import test_connection


# Override test methods
class EnhancedTester(test_connection.ConnectionTester):
    @staticmethod
    async def test_minimax(api_key: str, api_base: Optional[str] = None, 
                        model: Optional[str] = None) -> tuple[bool, str]:
        return await test_minimax_detailed(api_key, api_base, model)
    
    @staticmethod
    async def test_deepseek(api_key: str, api_base: Optional[str] = None, 
                         model: Optional[str] = None) -> tuple[bool, str]:
        return await test_deepseek_detailed(api_key, api_base, model)


def test_provider_sync_enhanced(provider, model: Optional[str] = None):
    """Enhanced sync test."""
    return asyncio.run(EnhancedTester.test_provider(provider, model))
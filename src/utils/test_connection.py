"""Утилиты для тестирования соединений с провайдерами."""

import httpx
import asyncio
from typing import Optional


class ConnectionTester:
    """Тестировщик соединений с LLM провайдерами."""
    
    @staticmethod
    async def test_deepseek(api_key: str, api_base: Optional[str] = None, model: Optional[str] = None) -> tuple[bool, str]:
        """Тест соединения с DeepSeek API."""
        base = api_base or "https://api.deepseek.com/v1/"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                # Try models endpoint first
                response = await client.get(
                    f"{base}models",
                    headers=headers
                )
                
                if response.status_code == 200:
                    return True, "Соединение успешно (models endpoint)"
                elif response.status_code == 401:
                    return False, "Неверный API ключ"
                elif response.status_code == 403:
                    return False, "Доступ запрещён"
                else:
                    # Try chat completions with a simple model as backup
                    if model:
                        chat_response = await client.post(
                            f"{base}chat/completions",
                            headers=headers,
                            json={"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 1}
                        )
                        if chat_response.status_code in (200, 201):
                            return True, "Соединение успешно (chat endpoint)"
                        elif chat_response.status_code == 401:
                            return False, "Неверный API ключ"
                        elif chat_response.status_code == 404:
                            return False, "Модель не найдена"
                        else:
                            return False, f"Ошибка: {chat_response.status_code}"
                    
                    return False, f"Ошибка: {response.status_code}"
                    
        except httpx.TimeoutException:
            return False, "Таймаут соединения"
        except Exception as e:
            return False, f"Ошибка: {str(e)}"
    
    @staticmethod
    async def test_moonshot(api_key: str, api_base: Optional[str] = None, model: Optional[str] = None) -> tuple[bool, str]:
        """Тест соединения с Moonshot AI API."""
        base = api_base or "https://api.moonshot.ai/v1/"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                response = await client.get(
                    f"{base}models",
                    headers=headers
                )
                
                if response.status_code == 200:
                    return True, "Соединение успешно"
                elif response.status_code == 401:
                    return False, "Неверный API ключ"
                elif response.status_code == 404:
                    if model:
                        chat_response = await client.post(
                            f"{base}chat/completions",
                            headers=headers,
                            json={"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 1}
                        )
                        if chat_response.status_code in (200, 201):
                            return True, "Соединение успешно"
                        elif chat_response.status_code == 404:
                            return False, "Модель не найдена"
                    return False, "Модели endpoint не найден"
                else:
                    return False, f"Ошибка: {response.status_code}"
                    
        except httpx.TimeoutException:
            return False, "Таймаут соединения"
        except Exception as e:
            return False, f"Ошибка: {str(e)}"
    
    @staticmethod
    async def test_minimax(api_key: str, api_base: Optional[str] = None, model: Optional[str] = None) -> tuple[bool, str]:
        """Тест соединения с Minimax AI API."""
        base = api_base or "https://api.minimax.chat/v1/text/"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                # Try different possible endpoints
                endpoints = [
                    f"{base}v1/models",
                    f"{base}models",
                ]
                
                for endpoint in endpoints:
                    try:
                        response = await client.get(endpoint, headers=headers)
                        if response.status_code == 200:
                            return True, "Соединение успешно"
                    except:
                        continue
                
                # If model specified, try chat completions
                if model:
                    chat_endpoint = base + "v1/chatcompletion_v3"
                    chat_response = await client.post(
                        chat_endpoint,
                        headers=headers,
                        json={
                            "model": model, 
                            "messages": [{"role": "user", "content": "Hi"}], 
                            "max_tokens": 1
                        }
                    )
                    if chat_response.status_code in (200, 201):
                        return True, "Соединение успешно"
                    elif chat_response.status_code == 404:
                        return False, "Модель не найдена"
                    elif chat_response.status_code == 400:
                        return False, f"Требуется модель: {chat_response.text[:100]}"
                        
                return False, "Не удалось подключиться (попробуйте chat endpoint)"
                    
        except httpx.TimeoutException:
            return False, "Таймаут соединения"
        except httpx.ConnectError:
            return False, "Не удалось подключиться к серверу"
        except Exception as e:
            return False, f"Ошибка: {str(e)}"
    
    @staticmethod
    async def test_custom(api_key: str, api_base: str, model: Optional[str] = None) -> tuple[bool, str]:
        """Тест соединения с кастомным OpenAI-совместимым API."""
        if not api_base:
            return False, "API Base не указан"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                base = api_base.rstrip('/')
                
                # Try models endpoint first
                response = await client.get(f"{base}/models", headers=headers)
                
                if response.status_code == 200:
                    return True, "Соединение успешно"
                
                if response.status_code == 401:
                    return False, "Неверный API ключ"
                
                if response.status_code == 404:
                    if model:
                        # Try with chat completions
                        chat_resp = await client.post(
                            f"{base}/chat/completions",
                            headers=headers,
                            json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
                        )
                        if chat_resp.status_code in (200, 201):
                            return True, "Соединение успешно (chat)"
                        elif chat_resp.status_code == 404:
                            return False, "Модель не найдена"
                        elif chat_resp.status_code == 400:
                            return False, chat_resp.text[:100]
                        else:
                            return False, f"Chat error {chat_resp.status_code}: {chat_resp.text[:50]}"
                    
                    return False, "endpoint /models недоступен"
                
                return False, f"Ошибка: {response.status_code}"
                    
        except httpx.TimeoutException:
            return False, "Таймаут соединения"
        except httpx.ConnectError:
            return False, "Не удалось подключиться к серверу"
        except Exception as e:
            return False, f"Ошибка: {str(e)}"
    
    @staticmethod
    async def test_openai(api_key: str, api_base: Optional[str] = None, model: Optional[str] = None) -> tuple[bool, str]:
        """Тест соединения с OpenAI API."""
        return await ConnectionTester.test_custom(api_key, api_base or "https://api.openai.com/v1/", model)
    
    @staticmethod
    async def test_anthropic(api_key: str, api_base: Optional[str] = None, model: Optional[str] = None) -> tuple[bool, str]:
        """Тест соединения с Anthropic API."""
        base = (api_base or "https://api.anthropic.com/").rstrip("/") + "/"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"
                }
                
                # Anthropic doesn't have /models endpoint, use messages
                if model:
                    response = await client.post(
                        f"{base}v1/messages",
                        headers=headers,
                        json={
                            "model": model, 
                            "max_tokens": 1,
                            "messages": [{"role": "user", "content": "hi"}]
                        }
                    )
                    
                    if response.status_code == 200:
                        return True, "Соединение успешно"
                    elif response.status_code == 401:
                        return False, "Неверный API ключ"
                    elif response.status_code == 404:
                        return False, "Модель не найдена"
                    elif response.status_code == 400:
                        try:
                            err = response.json()
                            return False, err.get("error", {}).get("message", str(err))[:100]
                        except:
                            return False, f"Ошибка: {response.status_code}"
                
                # Just list models (different endpoint)
                resp = await client.get(f"{base}v1/models", headers=headers)
                if resp.status_code == 200:
                    return True, "Соединение успешно"
                elif resp.status_code == 401:
                    return False, "Неверный API ключ"
                else:
                    return False, f"Ошибка: {resp.status_code}"
                    
        except httpx.TimeoutException:
            return False, "Таймаут соединения"
        except Exception as e:
            return False, f"Ошибка: {str(e)}"
    
    @staticmethod
    async def test_google(api_key: str, api_base: Optional[str] = None, model: Optional[str] = None) -> tuple[bool, str]:
        """Тест соединения с Google Generative Language API."""
        base = api_base or "https://generativelanguage.googleapis.com/v1/"
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                params = {"key": api_key}
                
                # Use models endpoint
                response = await client.get(f"{base}models", params=params)
                
                if response.status_code == 200:
                    return True, "Соединение успешно"
                elif response.status_code == 400:
                    return False, "Неверный API ключ"
                else:
                    return False, f"Ошибка: {response.status_code}"
                    
        except httpx.TimeoutException:
            return False, "Таймаут соединения"
        except Exception as e:
            return False, f"Ошибка: {str(e)}"
    
    @classmethod
    async def test_provider(cls, provider, model: Optional[str] = None) -> tuple[bool, str]:
        """Универсальный метод тестирования провайдера."""
        api_key = provider.api_key
        
        # Handle env: variables
        if api_key.startswith("env:"):
            import os
            env_var = api_key[4:]
            resolved = os.environ.get(env_var)
            if not resolved:
                return False, f"Переменная {env_var} не найдена"
            api_key = resolved
        
        # Check for obvious placeholders
        if api_key in ("", "sk-", "sk-.", "sk-.."):
            return False, "API ключ является плейсхолдером"
        
        if "...." in api_key:
            return False, "API ключ является плейсхолдером"
        
        api_type = provider.api_type
        api_base = provider.api_base
        
        if api_type == "open_ai":
            return await cls.test_openai(api_key, api_base, model)
        elif api_type == "anthropic":
            return await cls.test_anthropic(api_key, api_base, model)
        elif api_type == "google":
            return await cls.test_google(api_key, api_base, model)
        elif api_type == "deepseek":
            return await cls.test_deepseek(api_key, api_base, model)
        elif api_type == "moonshot":
            return await cls.test_moonshot(api_key, api_base, model)
        elif api_type == "minimax":
            return await cls.test_minimax(api_key, api_base, model)
        elif api_type == "custom":
            return await cls.test_custom(api_key, api_base, model)
        else:
            return False, "Неизвестный тип провайдера"

    @classmethod
    async def test_provider_with_model(cls, provider, model: Optional[str] = None) -> tuple[bool, str]:
        """Тест с опциональной моделью."""
        model = model or provider.model
        if model is None:
            # Try reasonable defaults
            defaults = {
                "deepseek": "deepseek-chat",
                "moonshot": "moonshot-v1-8k",
                "minimax": "abab6.5s-chat",
                "open_ai": "gpt-3.5-turbo",
                "anthropic": "claude-3-haiku-20240307",
            }
            model = defaults.get(provider.api_type)

        return await cls.test_provider(provider, model)



def test_provider_sync(provider, model: Optional[str] = None):
    """Синхронный тест провайдера."""
    return asyncio.run(ConnectionTester.test_provider_with_model(provider, model))
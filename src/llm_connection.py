"""Подключение к OpenAI-совместимым API напрямую через openai SDK.

microcore (стандартный бэкенд lm-proxy) теряет tool_calls в ответах:
в стриминге передаёт в callback только текст, а в обычных ответах
возвращает строку вместо объекта с choices. Это подключение передаёт
lm_proxy сырые объекты openai SDK, поэтому tool calls работают.
"""

import inspect

import openai


class OpenAIConnection:
    """Асинхронное подключение к OpenAI-совместимому API для lm-proxy."""

    def __init__(self, api_key=None, api_base=None, model=None,
                 default_headers=None, **_ignored):
        self.client = openai.AsyncOpenAI(
            api_key=api_key or "not-set",
            base_url=api_base or None,
            default_headers=default_headers,
        )
        self.default_model = model

    async def __call__(self, prompt, callback=None, **kwargs):
        messages = [self._to_dict(m) for m in (prompt if isinstance(prompt, list) else [prompt])]
        stream = bool(kwargs.pop("stream", False)) or callback is not None
        if self.default_model and not kwargs.get("model"):
            kwargs["model"] = self.default_model

        if stream:
            return await self._stream(messages, callback, **kwargs)
        response = await self.client.chat.completions.create(
            messages=messages, stream=False, **kwargs
        )
        if getattr(response, "object", None) == "error":
            raise RuntimeError(f"Upstream API error: {response}")
        return response

    async def _stream(self, messages, callback, **kwargs):
        response = await self.client.chat.completions.create(
            messages=messages, stream=True, **kwargs
        )
        text = ""
        async for chunk in response:
            if callback is not None:
                result = callback(chunk)
                if inspect.isawaitable(result):
                    await result
            try:
                if chunk.choices and chunk.choices[0].delta.content:
                    text += chunk.choices[0].delta.content
            except (AttributeError, IndexError):
                pass
        return text

    @staticmethod
    def _to_dict(message):
        if isinstance(message, dict):
            return message
        if hasattr(message, "role") and hasattr(message, "content"):
            return {"role": str(message.role), "content": message.content}
        return {"role": "user", "content": str(message)}

"""Подключение к OpenAI-совместимым API напрямую через openai SDK.

microcore (стандартный бэкенд lm-proxy) теряет tool_calls в ответах:
в стриминге передаёт в callback только текст, а в обычных ответах
возвращает строку вместо объекта с choices. Это подключение передаёт
lm_proxy сырые объекты openai SDK (нестрим) и текстовые дельты (стрим —
lm_proxy оборачивает callback-пayload в {"content": str(block)}),
поэтому tool calls работают.
"""

import inspect
import json
import os
import sys
import threading
import time
from datetime import datetime

import openai


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class RequestLogger:
    """Логирует запросы и ответы LLM в stdout и (опционально) в файл."""

    def __init__(self, enabled=None, log_file=None, max_chars=50000):
        self.enabled = _env_flag("LLM_PROXY_LOG", True) if enabled is None else enabled
        self.log_file = log_file or os.environ.get("LLM_PROXY_LOG_FILE") or "llm_requests.log"
        self.max_chars = max_chars
        self._lock = threading.Lock()
        self._counter = 0
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass

    def next_id(self):
        with self._lock:
            self._counter += 1
            return self._counter

    @staticmethod
    def _dump(data):
        try:
            return json.dumps(data, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):
            return str(data)

    def write(self, request_id, connection, event, data=None):
        if not self.enabled:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        header = f"[LLM #{request_id}] [{connection}] [{timestamp}] {event}"
        text = header
        if data is not None:
            body = self._dump(data)
            if len(body) > self.max_chars:
                body = body[: self.max_chars] + f"\n... <обрезано, всего {len(body)} символов>"
            text = f"{header}\n{body}"
        with self._lock:
            print(text, flush=True)
            if self.log_file:
                try:
                    with open(self.log_file, "a", encoding="utf-8") as f:
                        f.write(text + "\n\n")
                except OSError:
                    pass


class OpenAIConnection:
    """Асинхронное подключение к OpenAI-совместимому API для lm-proxy."""

    def __init__(self, api_key=None, api_base=None, model=None,
                 default_headers=None, name=None, log_requests=None,
                 log_file=None, **_ignored):
        self.client = openai.AsyncOpenAI(
            api_key=api_key or "not-set",
            base_url=api_base or None,
            default_headers=default_headers,
        )
        self.default_model = model
        self.name = name or api_base or "openai"
        self.logger = RequestLogger(enabled=log_requests, log_file=log_file)

    async def __call__(self, prompt, callback=None, **kwargs):
        messages = [self._to_dict(m) for m in (prompt if isinstance(prompt, list) else [prompt])]
        stream = bool(kwargs.pop("stream", False)) or callback is not None
        if self.default_model and not kwargs.get("model"):
            kwargs["model"] = self.default_model

        request_id = self.logger.next_id()
        started = time.monotonic()
        self.logger.write(request_id, self.name, ">>> ЗАПРОС", {
            "model": kwargs.get("model"),
            "stream": stream,
            "messages": messages,
            **{k: v for k, v in kwargs.items() if k not in ("model",)},
        })
        try:
            if stream:
                result = await self._stream(messages, callback, _request_id=request_id, **kwargs)
            else:
                result = await self._request(messages, _request_id=request_id, **kwargs)
        except Exception as error:
            self.logger.write(request_id, self.name,
                              f"!!! ОШИБКА после {time.monotonic() - started:.1f}с: {error}")
            raise
        return result

    async def _request(self, messages, _request_id=None, **kwargs):
        started = time.monotonic()
        response = await self.client.chat.completions.create(
            messages=messages, stream=False, **kwargs
        )
        if getattr(response, "object", None) == "error":
            raise RuntimeError(f"Upstream API error: {response}")
        data = response.model_dump() if hasattr(response, "model_dump") else response
        self.logger.write(_request_id, self.name,
                          f"<<< ОТВЕТ за {time.monotonic() - started:.1f}с", data)
        return response

    async def _stream(self, messages, callback, _request_id=None, **kwargs):
        started = time.monotonic()
        response = await self.client.chat.completions.create(
            messages=messages, stream=True, **kwargs
        )
        text = ""
        tool_calls = {}
        finish_reason = None
        async for chunk in response:
            try:
                choice = chunk.choices[0] if chunk.choices else None
                if choice is None:
                    continue
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                if delta.content:
                    text += delta.content
                    if callback is not None:
                        result = callback(delta.content)
                        if inspect.isawaitable(result):
                            await result
                for tc in getattr(delta, "tool_calls", None) or []:
                    slot = tool_calls.setdefault(tc.index, {
                        "id": "", "type": "function",
                        "function": {"name": "", "arguments": ""},
                    })
                    if tc.id:
                        slot["id"] += tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            slot["function"]["arguments"] += tc.function.arguments
            except (AttributeError, IndexError):
                pass
        summary = {"finish_reason": finish_reason, "content": text}
        if tool_calls:
            summary["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
        self.logger.write(_request_id, self.name,
                          f"<<< СТРИМ ЗАВЕРШЁН за {time.monotonic() - started:.1f}с", summary)
        return text

    @staticmethod
    def _to_dict(message):
        if isinstance(message, dict):
            return message
        if hasattr(message, "role") and hasattr(message, "content"):
            return {"role": str(message.role), "content": message.content}
        return {"role": "user", "content": str(message)}

"""Утилиты для подсчёта токенов с использованием tiktoken."""

import tiktoken
from typing import Optional


# Доступные кодировки (имя -> описание)
ENCODINGS = {
    "cl100k_base": "CL100K Base (GPT-4, GPT-3.5, GPT-4O)",
    "o200k_base": "O200K Base (GPT-4O最新的)",
    "p50k_base": "P50K Base (Codex)",
    "r50k_base": "R50K Base (早期 GPT模型)",
}


def get_encoding(encoding_name: str) -> Optional["tiktoken.Encoding"]:
    """Получить объект кодировки по имени."""
    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception as e:
        print(f"Ошибка получения кодировки {encoding_name}: {e}")
        return None


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Подсчитать количество токенов в тексте."""
    encoding = get_encoding(encoding_name)
    if encoding is None:
        return 0
    
    try:
        tokens = encoding.encode(text)
        return len(tokens)
    except Exception as e:
        print(f"Ошибка кодирования текста: {e}")
        return 0


def count_messages_tokens(messages: list[dict], encoding_name: str = "cl100k_base") -> dict:
    """
    Подсчитать токены для списка сообщений.
    
    messages: [{"role": "system|user|assistant", "content": "..."}]
    """
    encoding = get_encoding(encoding_name)
    if encoding is None:
        return {"total": 0, "system": 0, "user": 0, "assistant": 0}
    
    total_tokens = 0
    tokens_by_role = {"system": 0, "user": 0, "assistant": 0}
    
    try:
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Добавляем форматирование для каждой роли
            if role == "system":
                text = f"System: {content}"
            elif role == "user":
                text = f"User: {content}"
            elif role == "assistant":
                text = f"Assistant: {content}"
            else:
                text = content
            
            num_tokens = len(encoding.encode(text))
            tokens_by_role[role] = tokens_by_role.get(role, 0) + num_tokens
            total_tokens += num_tokens
        
        # Добавляем overhead для каждого сообщения (обычно 3-4 токена)
        overhead = 3 * len(messages)
        total_tokens += overhead
        
        tokens_by_role["total"] = total_tokens
        return tokens_by_role
    except Exception as e:
        print(f"Ошибка подсчёта токенов: {e}")
        return {"total": 0, "system": 0, "user": 0, "assistant": 0}


def estimate_cost(tokens: int, model: str = "gpt-3.5-turbo", encoding_name: str = "cl100k_base") -> float:
    """
    Оценить стоимость в USD.
    
    Приблизительные цены за 1M токенов (могут меняться):
    - GPT-4: $30 prompt, $60 completion
    - GPT-4 Turbo: $10 prompt, $30 completion  
    - GPT-3.5 Turbo: $0.5 prompt, $1.5 completion
    - GPT-4O: $2.5 prompt, $10 completion
    - GPT-4O Mini: $0.075 prompt, $0.3 completion
    """
    pricing = {
        "gpt-4": {"prompt": 30.0, "completion": 60.0},
        "gpt-4-turbo": {"prompt": 10.0, "completion": 30.0},
        "gpt-3.5-turbo": {"prompt": 0.5, "completion": 1.5},
        "gpt-4o": {"prompt": 2.5, "completion": 10.0},
        "gpt-4o-mini": {"prompt": 0.075, "completion": 0.3},
    }
    
    # Находим наиболее подходящую модель
    model_lower = model.lower()
    matched_price = None
    
    for key, price in pricing.items():
        if key in model_lower:
            matched_price = price
            break
    
    if matched_price is None:
        # По умолчанию используем GPT-3.5 цены
        matched_price = pricing["gpt-3.5-turbo"]
    
    # Средняя цена (упрощённо)
    avg_price = (matched_price["prompt"] + matched_price["completion"]) / 2
    
    return (tokens / 1_000_000) * avg_price


def get_available_models(encoding_name: str) -> list[str]:
    """Получить список доступных моделей для кодировки."""
    mapping = {
        "cl100k_base": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "gpt-4o"],
        "o200k_base": ["gpt-4o", "gpt-4o-mini"],
        "p50k_base": ["codex-davinci-002", "code-davinci-002"],
        "r50k_base": ["gpt-3.5-turbo", "text-davinci-003"],
    }
    return mapping.get(encoding_name, [])
"""Модели данных для LLM Proxy Server GUI."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Provider:
    """Модель провайдера."""
    name: str = ""
    api_type: str = "open_ai"
    api_base: Optional[str] = None
    api_key: str = ""
    model: Optional[str] = None  # Default модель
    enabled: bool = True
    reasoning_effort: Optional[str] = None  # low/medium/high/max (DeepSeek thinking)
    thinking: bool = False  # DeepSeek thinking mode toggle


@dataclass
class RoutingRule:
    """Правило маршрутизации."""
    model_pattern: str = ""
    connection: str = ""
    target_model: str = ""


@dataclass
class Group:
    """Группа пользователей."""
    name: str = ""
    api_keys: list[str] = field(default_factory=list)
    allowed_connections: str = "*"


@dataclass 
class ServerConfig:
    """Конфигурация сервера."""
    host: str = "0.0.0.0"
    port: int = 8000
    dev_autoreload: bool = False


@dataclass
class AppConfig:
    """Главная конфигурация приложения."""
    version: str = "1.0"
    server: ServerConfig = field(default_factory=lambda: ServerConfig())
    connections: list[Provider] = field(default_factory=list)
    routing: list[RoutingRule] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    listing_mode: str = "as_is"
    response_model: str = "gpt-4o"


# Встроенные провайдеры
BUILTIN_PROVIDERS = {
    "deepseek": Provider(
        name="deepseek",
        api_type="open_ai",
        api_base="https://api.deepseek.com/v1/",
        api_key="env:DEEPSEEK_API_KEY",
        enabled=True
    ),
    "moonshot": Provider(
        name="moonshot",
        api_type="open_ai",
        api_base="https://api.moonshot.ai/v1/",
        api_key="env:MOONSHOT_API_KEY",
        enabled=True
    ),
    "minimax": Provider(
        name="minimax",
        api_type="open_ai",
        api_base="https://api.minimax.chat/v1/text/",
        api_key="env:MINIMAX_API_KEY",
        enabled=True
    ),
}


# Список типов провайдеров
PROVIDER_TYPES = [
    ("open_ai", "DeepSeek"),
    ("moonshot", "Moonshot AI"),
    ("minimax", "Minimax AI"),
    ("anthropic", "Anthropic"),
    ("google", "Google (Generative Language)"),
    ("google_vertex", "Google Vertex AI"),
    ("custom", "Custom (OpenAI-compatible)"),
]


# Доступные кодировки tiktoken
ENCODINGS_DICT = {
    "cl100k_base": "CL100K Base (GPT-4, GPT-3.5)",
    "o200k_base": "O200K Base (GPT-4O)",
    "p50k_base": "P50K Base (Codex)",
    "r50k_base": "R50K Base (Early GPT)",
}
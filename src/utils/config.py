"""Утилиты для работы с конфигурацией JSON."""

import json
import os
from typing import Optional

from src.models import AppConfig, Provider, RoutingRule, Group


DEFAULT_CONFIG_PATH = "llm_proxy_config.json"


def get_default_config_path() -> str:
    """Получить путь к конфигурации по умолчанию."""
    return DEFAULT_CONFIG_PATH


def create_default_config() -> AppConfig:
    """Создать конфигурацию по умолчанию."""
    config = AppConfig()
    # Добавляем встроенные провайдеры как отключенные по умолчанию
    config.connections.append(Provider(
        name="deepseek", 
        api_type="open_ai", 
        api_base="https://api.deepseek.com/v1/", 
        api_key="env:DEEPSEEK_API_KEY", 
        enabled=False
    ))
    config.connections.append(Provider(
        name="moonshot", 
        api_type="open_ai", 
        api_base="https://api.moonshot.ai/v1/", 
        api_key="env:MOONSHOT_API_KEY", 
        enabled=False
    ))
    config.connections.append(Provider(
        name="minimax", 
        api_type="open_ai", 
        api_base="https://api.minimax.io/anthropic", 
        api_key="env:MINIMAX_API_KEY", 
        enabled=False
    ))
    
    # Добавляем группу по умолчанию
    config.groups.append(Group(name="default", api_keys=["YOUR_API_KEY_HERE"], allowed_connections="*"))
    
    return config


def config_to_dict(config: AppConfig) -> dict:
    """Преобразовать конфигурацию в словарь."""
    return {
        "version": config.version,
        "server": {
            "host": config.server.host,
            "port": config.server.port,
            "dev_autoreload": config.server.dev_autoreload,
        },
        "listing_mode": config.listing_mode,
        "response_model": config.response_model,
        "connections": [
            {
                "name": c.name,
                "api_type": c.api_type,
                "api_base": c.api_base,
                "api_key": c.api_key,
                "model": c.model,
                "enabled": c.enabled,
                "reasoning_effort": c.reasoning_effort,
                "thinking": c.thinking,
            }
            for c in config.connections
        ],
        "routing": [
            {
                "model_pattern": r.model_pattern,
                "connection": r.connection,
                "target_model": r.target_model,
            }
            for r in config.routing
        ],
        "groups": [
            {
                "name": g.name,
                "api_keys": g.api_keys,
                "allowed_connections": g.allowed_connections,
            }
            for g in config.groups
        ],
    }


def dict_to_config(d: dict) -> AppConfig:
    """Преобразовать словарь в конфигурацию."""
    config = AppConfig()
    config.version = d.get("version", "1.0")
    config.listing_mode = d.get("listing_mode", "as_is")
    config.response_model = d.get("response_model", "gpt-4o")
    
    server = d.get("server", {})
    config.server.host = server.get("host", "0.0.0.0")
    config.server.port = server.get("port", 8000)
    config.server.dev_autoreload = server.get("dev_autoreload", False)
    
    config.connections = [
        Provider(
            name=c["name"],
            api_type=c.get("api_type", "open_ai"),
            api_base=c.get("api_base"),
            api_key=c.get("api_key", ""),
            model=c.get("model"),
            enabled=c.get("enabled", True),
            reasoning_effort=c.get("reasoning_effort"),
            thinking=c.get("thinking", False),
        )
        for c in d.get("connections", [])
    ]
    
    config.routing = [
        RoutingRule(
            model_pattern=r["model_pattern"],
            connection=r["connection"],
            target_model=r.get("target_model", r.get("model_name", "")),
        )
        for r in d.get("routing", [])
    ]
    
    config.groups = [
        Group(
            name=g["name"],
            api_keys=g.get("api_keys", []),
            allowed_connections=g.get("allowed_connections", "*"),
        )
        for g in d.get("groups", [])
    ]
    
    return config


def save_config(config: AppConfig, filepath: Optional[str] = None) -> bool:
    """Сохранить конфигурацию в JSON файл."""
    if filepath is None:
        filepath = get_default_config_path()
    
    try:
        config_dict = config_to_dict(config)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"Ошибка сохранения конфигурации: {e}")
        return False


def load_config(filepath: Optional[str] = None) -> Optional[AppConfig]:
    """Загрузить конфигурацию из JSON файла."""
    if filepath is None:
        filepath = get_default_config_path()
    
    if not os.path.exists(filepath):
        return create_default_config()
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)
        
        return dict_to_config(config_dict)
    except Exception as e:
        print(f"Ошибка загрузки конфигурации: {e}")
        return create_default_config()


def config_to_toml(config: AppConfig) -> str:
    """Преобразовать конфигурацию в формат TOML для llm-proxy-server."""
    lines = []
    
    # Server section
    lines.append(f'host = "{config.server.host}"')
    lines.append(f'port = {config.server.port}')
    lines.append(f'dev_autoreload = {str(config.server.dev_autoreload).lower()}')
    lines.append(f'model_listing_mode = "{config.listing_mode}"')
    lines.append('api_key_check = "lm_proxy.api_key_check.allow_all.AllowAll"')
    lines.append("")
    
    # Connections
    if config.connections:
        lines.append("[connections]")
        for conn in config.connections:
            lines.append(f'[connections.{conn.name}]')
            lines.append(f'api_type = "{conn.api_type}"')
            if conn.api_base:
                lines.append(f'api_base = "{conn.api_base}"')
            lines.append(f'api_key = "{conn.api_key}"')
            if conn.model:
                lines.append(f'model = "{conn.model}"')
            lines.append("")

    # Default params
    for conn in config.connections:
        if conn.reasoning_effort or conn.thinking:
            if not any(line.startswith("[default_params]") for line in lines):
                lines.append("[default_params]")
            lines.append(f'[default_params.{conn.name}]')
            if conn.reasoning_effort:
                lines.append(f'reasoning_effort = "{conn.reasoning_effort}"')
            if conn.thinking:
                lines.append('thinking = true')
            lines.append("")
    
    # Routing
    if config.routing:
        lines.append("[routing]")
        for route in config.routing:
            lines.append(f'"{route.model_pattern}" = "{route.connection}.{route.target_model}"')
        lines.append("")
    
    # Groups
    if config.groups:
        lines.append("[groups]")
        for group in config.groups:
            lines.append(f'[groups.{group.name}]')
            lines.append(f'api_keys = {json.dumps(group.api_keys)}')
            lines.append(f'allowed_connections = "{group.allowed_connections}"')
            lines.append("")
    
    return "\n".join(lines)


def get_env_template() -> str:
    """Получить шаблон .env файла."""
    return '''# DeepSeek API Key
DEEPSEEK_API_KEY=sk-............

# Moonshot AI API Key
MOONSHOT_API_KEY=............

# Minimax AI API Key
MINIMAX_API_KEY=............

# OpenAI API Key (optional)
OPENAI_API_KEY=sk-..........

# Anthropic API Key (optional)
ANTHROPIC_API_KEY=sk-ant-api03-..........

# Google API Key (optional)
GOOGLE_API_KEY=AIza..........

# Google Vertex AI API Key (optional)
GOOGLE_VERTEX_API_KEY=..........

# Debug mode (1 = enabled, 0 = disabled)
LM_PROXY_DEBUG=0
'''


def validate_provider(provider: Provider) -> tuple[bool, str]:
    """Валидировать провайдер."""
    errors = []
    
    if not provider.name.strip():
        errors.append("Имя провайдера не может быть пустым")
    
    if not provider.api_key.strip():
        errors.append("API ключ не может быть пустым")
    
    if provider.api_key.startswith("env:") and len(provider.api_key) < 5:
        errors.append("Неверный формат переменной окружения (пример: env:VAR_NAME)")
    
    if errors:
        return False, "; ".join(errors)
    
    return True, "OK"


def validate_routing_rule(rule: RoutingRule, connections: list[Provider]) -> tuple[bool, str]:
    """Валидировать правило маршрутизации."""
    errors = []
    
    if not rule.model_pattern.strip():
        errors.append("Паттерн модели не может быть пустым")
    
    if not rule.connection.strip():
        errors.append("Имя подключения не может быть пустым")
    
    connection_names = [c.name for c in connections]
    if rule.connection not in connection_names:
        errors.append(f"Подключение '{rule.connection}' не найдено в списке провайдеров")
    
    if not rule.target_model.strip():
        errors.append("Имя модели не может быть пустым")
    
    if errors:
        return False, "; ".join(errors)
    
    return True, "OK"


def validate_group(group: Group) -> tuple[bool, str]:
    """Валидировать группу."""
    errors = []
    
    if not group.name.strip():
        errors.append("Имя группы не может быть пустым")
    
    if not group.api_keys:
        errors.append("Группа должна содержать хотя бы один API ключ")
    
    if errors:
        return False, "; ".join(errors)
    
    return True, "OK"
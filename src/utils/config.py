"""Утилиты для работы с конфигурацией JSON."""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from src.models import AppConfig, Provider, RoutingRule, Group


_BARE_TOML_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def toml_key(key: str) -> str:
    if _BARE_TOML_KEY_RE.match(key):
        return key
    return '"' + key.replace("\\", "\\\\").replace('"', '\\"') + '"'


def toml_str(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


APP_NAME = "ProxyLLM"
CONFIG_DIR_ENV = "LLM_PROXY_CONFIG_DIR"
DEFAULT_CONFIG_FILENAME = "llm_proxy_config.json"


def get_app_data_dir() -> str:
    custom_dir = os.environ.get(CONFIG_DIR_ENV)
    if custom_dir:
        return str(Path(custom_dir).expanduser().resolve())

    if os.name == "nt":
        windows_dir = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if windows_dir:
            return str(Path(windows_dir) / APP_NAME)

    config_home = os.environ.get("XDG_CONFIG_HOME")
    base_dir = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return str(base_dir / APP_NAME)


def get_bundled_default_config_path() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).resolve().parents[2]
    return str(base_dir / DEFAULT_CONFIG_FILENAME)


def get_default_config_path() -> str:
    """Получить путь к конфигурации по умолчанию."""
    return str(Path(get_app_data_dir()) / DEFAULT_CONFIG_FILENAME)


def create_default_config() -> AppConfig:
    """Создать конфигурацию по умолчанию."""
    bundled_path = get_bundled_default_config_path()
    try:
        with open(bundled_path, "r", encoding="utf-8") as f:
            return dict_to_config(json.load(f))
    except (OSError, ValueError, KeyError, TypeError):
        pass

    config = AppConfig()
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
                "temperature": c.temperature,
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
            temperature=c.get("temperature"),
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
        config_path = Path(filepath).expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open('w', encoding='utf-8') as f:
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
        config = create_default_config()
        save_config(config, filepath)
        return config
    
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
    enabled_connections = [c for c in config.connections if c.enabled]
    enabled_names = {c.name for c in enabled_connections}

    # Server section
    lines.append(f'host = {toml_str(config.server.host)}')
    lines.append(f'port = {config.server.port}')
    lines.append(f'dev_autoreload = {str(config.server.dev_autoreload).lower()}')
    lines.append(f'model_listing_mode = {toml_str(config.listing_mode)}')
    lines.append('api_key_check = "lm_proxy.api_key_check.allow_all.AllowAll"')
    lines.append("")

    # Connections
    if enabled_connections:
        lines.append("[connections]")
        for conn in enabled_connections:
            lines.append(f'[connections.{toml_key(conn.name)}]')
            if conn.api_type in ("open_ai", "custom"):
                lines.append('class = "src.llm_connection.OpenAIConnection"')
                lines.append(f'name = {toml_str(conn.name)}')
                lines.append('log_requests = true')
            else:
                lines.append(f'api_type = {toml_str(conn.api_type)}')
            if conn.api_base:
                lines.append(f'api_base = {toml_str(conn.api_base)}')
            lines.append(f'api_key = {toml_str(conn.api_key)}')
            if conn.model:
                lines.append(f'model = {toml_str(conn.model)}')
            lines.append("")

    default_connections = [
        connection
        for connection in enabled_connections
        if connection.reasoning_effort or connection.thinking
    ]
    force_connections = [
        connection
        for connection in enabled_connections
        if connection.temperature is not None
    ]
    if default_connections or force_connections:
        lines.append('[[before]]')
        lines.append('class = "src.server.ConnectionDefaultsHandler"')
        lines.append("")
        for connection in default_connections:
            lines.append(f'[before.defaults.{toml_key(connection.name)}]')
            if connection.reasoning_effort:
                lines.append(f'reasoning_effort = {toml_str(connection.reasoning_effort)}')
            if connection.thinking:
                lines.append('thinking = true')
            lines.append("")
        for connection in force_connections:
            lines.append(f'[before.force.{toml_key(connection.name)}]')
            lines.append(f'temperature = {float(connection.temperature)}')
            lines.append("")

    # Routing
    active_routing = [r for r in config.routing if r.connection in enabled_names]
    if active_routing:
        lines.append("[routing]")
        for route in active_routing:
            lines.append(f'{toml_str(route.model_pattern)} = {toml_str(f"{route.connection}.{route.target_model}")}')
        lines.append("")

    # Groups
    if config.groups:
        lines.append("[groups]")
        for group in config.groups:
            lines.append(f'[groups.{toml_key(group.name)}]')
            lines.append(f'api_keys = {json.dumps(group.api_keys)}')
            lines.append(f'allowed_connections = {toml_str(group.allowed_connections)}')
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
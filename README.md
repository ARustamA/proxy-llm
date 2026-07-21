# ProxyLLM

Графическая оболочка (tkinter) для [llm-proxy-server](https://pypi.org/project/llm-proxy-server/) — единая точка доступа к нескольким LLM-провайдерам (DeepSeek, Moonshot/Kimi, MiniMax, локальные модели и др.) через OpenAI-совместимый API.

## Возможности

- Управление провайдерами, маршрутизацией моделей и группами доступа через GUI
- Автогенерация `proxy_config.toml` при запуске сервера
- Поддержка tool calls (function calling) — соединение идёт напрямую через `openai` SDK (`src/llm_connection.py`)
- Подсчёт токенов и оценка стоимости (tiktoken)
- Тест соединения с провайдерами
- Умолчания на уровне подключения: `reasoning_effort`, режим thinking (`src/server.py`)
- Ключи можно хранить в переменных окружения (`env:VAR_NAME` вместо ключа)

## Требования

- Windows (скрипты управления портом используют `netstat`/`taskkill`)
- Python 3.12+

## Установка

```powershell
# Клонировать репозиторий
git clone <url-репозитория>
cd proxy-llm

# Создать виртуальное окружение
python -m venv .venv

# Активировать его
.venv\Scripts\Activate.ps1
# если PowerShell ругается на политику выполнения:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Установить зависимости (версии зафиксированы)
pip install -r requirements.txt
```

## Запуск

### GUI (рекомендуется)

```powershell
python main.py
```

GUI при старте генерирует `proxy_config.toml` из своей конфигурации и запускает `llm-proxy-server` как дочерний процесс. Управление — вкладка «Сервер» (Старт / Стоп / Рестарт).

### Без GUI (только прокси)

```powershell
llm-proxy-server --config proxy_config.toml
# с отладочными логами:
llm-proxy-server --config proxy_config.toml --debug
```

По умолчанию прокси слушает `0.0.0.0:8001`, эндпоинт — `http://localhost:8001/v1` (OpenAI-совместимый).

## Конфигурация

| Файл | Назначение |
|------|-----------|
| `%LOCALAPPDATA%\ProxyLLM\llm_proxy_config.json` | Основная конфигурация GUI (источник истины) |
| `proxy_config.toml` | Конфиг прокси-сервера, **пересоздаётся GUI при каждом запуске** — ручные правки будут затёрты, редактируйте через GUI |
| `.env` | Переменные окружения с API-ключами (подхватываются при старте) |

- API-ключ провайдера можно задать как `env:ИМЯ_ПЕРЕМЕННОЙ` — значение будет взято из окружения.
- Маршрутизация: имя модели из запроса → `подключение.модель` (поддерживаются wildcard-паттерны).
- Группы: виртуальные API-ключи клиентов и разрешённые подключения.
- Имена подключений могут содержать пробелы, но **не должны содержать точек** (маршрутизация разделяется по первой точке).

## Использование с клиентами

Направьте любой OpenAI-совместимый клиент на прокси:

```
OPENAI_BASE_URL=http://localhost:8001/v1
OPENAI_API_KEY=<ключ из группы в конфиге>
```

## Сборка exe

```powershell
pyinstaller ProxyLLM.spec
```

Готовый бинарь — в `dist\ProxyLLM.exe`.

## Структура проекта

```
main.py                  # GUI и управление процессом прокси
src/
  llm_connection.py      # Подключение к OpenAI-совместимым API (tool calls)
  server.py              # before-хук прокси: reasoning_effort / thinking
  models/                # Модели данных конфигурации
  utils/
    config.py            # JSON-конфиг + генерация TOML
    tokens.py            # Подсчёт токенов
    test_connection.py   # Тест соединения с провайдерами
```

## Устранение неполадок

- **«Cannot declare (...) twice» при старте** — невалидный TOML; чаще всего дублируется имя подключения. Исправьте конфигурацию через GUI (вкладка «Провайдеры»).
- **Порт занят** — кнопка «🔥 Форс» на вкладке «Сервер» убивает процесс на порту и перезапускает прокси.
- **Не работают tool calls** — убедитесь, что в `proxy_config.toml` у подключения указан `class = "src.llm_connection.OpenAIConnection"` (генерируется автоматически для типов `open_ai`/`custom`).
- **«llm-proxy-server not found»** — сервер не установлен или не активировано venv: `pip install -r requirements.txt`.
- **Ctrl+C/V не работает в полях ввода** — исправлено для русской раскладки и Caps Lock; если проявляется, проверьте раскладку клавиатуры.

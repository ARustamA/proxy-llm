# LLM Proxy Server GUI - Specification

## Project Overview

- **Project Name**: LLM Proxy Server GUI
- **Type**: Desktop GUI Application
- **Core Functionality**: Графическая оболочка для управления конфигурацией llm-proxy-server с поддержкой множества провайдеров и подсчётом токенов
- **Target Users**: Разработчики и администраторы, использующие llm-proxy-server

---

## UI/UX Specification

### Window Structure

- **Main Window**: Одно окно с вкладками (ttk.Notebook)
- **Dialog Windows**: Модальные диалоги для редактирования провайдеров и групп
- **Minimum Size**: 900x650 пикселей
- **Resizable**: Да

### Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  Заголовок: LLM Proxy Server GUI                           │
├─────────────────────────────────────────────────────────────┤
│  [Connections] [Routing] [Groups] [Token Counter] [Settings] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    Content Area                            │
│                  (根据选中标签页变化)                        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Status Bar: [Status] [Config Path]                       │
└─────────────────────────────────────────────────────────────┘
```

### Visual Design

#### Color Palette

- **Primary Background**: #1E1E2E (тёмный фон)
- **Secondary Background**: #2D2D3F (карточки)
- **Accent**: #7C3AED (фиолетовый акцент)
- **Success**: #10B981 (зелёный)
- **Warning**: #F59E0B (жёлтый)
- **Error**: #EF4444 (красный)
- **Text Primary**: #F8FAFC
- **Text Secondary**: #94A3B8
- **Border**: #3D3D5C

#### Typography

- **Font Family**: "Segoe UI", system-ui, sans-serif
- **Headings**: 16px bold
- **Body Text**: 13px regular
- **Small Text**: 11px
- **Monospace** (для API ключей): "Consolas", "Courier New", monospace

#### Spacing

- **Base Unit**: 8px
- **Card Padding**: 16px
- **Section Margin**: 24px
- **Element Gap**: 12px

#### Visual Effects

- **Cards**: Border-radius 8px, subtle border (#3D3D5C)
- **Buttons**: Border-radius 6px, hover effects
- **Focus States**: Accent color glow outline
- **Animations**: 150ms ease transitions

### Components

#### Tab 1: Connections (Провайдеры)

- **TreeView**: Список провайдеров с колонками (Name, Type, API Base, Status)
- **Action Buttons**: Add, Edit, Delete, Test Connection
- **Provider Types**: OpenAI, Anthropic, Google, Custom

#### Tab 2: Routing (Маршрутизация)

- **Table**: Model Pattern | Connection | Model Name
- **Action Buttons**: Add Route, Edit, Delete
- **Wildcard Support**: Отображение поддержки масок (gpt*, claude*)

#### Tab 3: Groups (Группы пользователей)

- **TreeView**: Group Name, API Keys Count, Allowed Connections
- **Action Buttons**: Add Group, Edit, Delete

#### Tab 4: Token Counter

- **Input Field**: Текстовое поле для ввода сообщения
- **Model Selector**: Выбор модели (dropdown)
- **Result Display**: Количество токенов, примерная стоимость
- **Encodings List**: cl100k_base, p50k_base, r50k_base

#### Tab 5: Settings

- **Server Settings**: Host, Port, Dev Autoreload
- **API Key Validator**: Выбор метода валидации
- **Logging Settings**: Логгеры и параметры
- **UI Settings**: Тема (только тёмная для v1)

---

## Functionality Specification

### Core Features

#### 1. Управление провайдерами

- Добавление нового провайдера с типом (OpenAI, Anthropic, Google, Custom)
- Редактирование существующего провайдера
- Удаление провайдера с подтверждением
- Тестирование соединения (ping)
- Поддержка environment variables (env:VAR_NAME синтаксис)

#### 2. Маршрутизация моделей

- Добавление правила маршрутизации (pattern → connection.model)
- Поддержка wildcard паттернов (\*)
- Приоритет правил (более специфичные выше)
- Автодополнение при выборе connection

#### 3. Группы пользователей

- Создание группы с именем
- Добавление API ключей в группу
- Настройка allowed_connections
- Валидация ключей

#### 4. Подсчёт токенов (Tiktoken)

- Ввод текста сообщения
- Выбор кодировки модели
- Подсчёт токенов для разных ролей (system, user, assistant)
- Общее количество токенов
- Оценка стоимости (по приблизительным ценам)

#### 5. Настройки сервера

- Host и Port
- Dev autoreload toggle
- Конфигурация логирования
- Выбор метода API key validation

### Data Flow

```
User Input → GUI Widgets → Data Models → JSON Config
                                             ↓
                              llm-proxy-server (TOML conversion)
```

### Edge Cases

- Пустые поля при валидации показывают ошибку
- Duplicate provider names запрещены
- Invalid API key формат показывает warning
- Network timeout при тесте соединения показывает error
- Invalid JSON файл показывает error с возможностью создать новый

---

## Data Structures

### Provider Model

```python
{
    "name": str,              # Уникальное имя
    "api_type": str,          # open_ai, anthropic, google, custom
    "api_base": str,         # URL базы (опционально)
    "api_key": str,          # API ключ или env:VAR_NAME
    "enabled": bool           # Включён
}
```

### Routing Rule Model

```python
{
    "model_pattern": str,     # Паттерн модели (* поддерживается)
    "connection": str,        # Имя подключения
    "model_name": str         # Имя модели на удалённом сервере
}
```

### Group Model

```python
{
    "name": str,              # Имя группы
    "api_keys": list[str],   # Список API ключей
    "allowed_connections": str  # * или comma-separated
}
```

### Configuration JSON Structure

```python
{
    "version": "1.0",
    "server": {
        "host": "0.0.0.0",
        "port": 8000,
        "dev_autoreload": False
    },
    "connections": [...],
    "routing": [...],
    "groups": [...],
    "api_key_check": {...},
    "loggers": [...]
}
```

---

## Acceptance Criteria

### Visual Checkpoints

- [ ] Приложение запускается без ошибок
- [ ] Все пять вкладок отображаются корректно
- [ ] Цветовая схема соответствует спецификации
- [ ] Окно изменяет размер, содержимое адаптируется
- [ ] Статус бар отображает путь к конфигурации

### Functional Checkpoints

- [ ] Можно добавить новый провайдер (OpenAI)
- [ ] Можно редактировать провайдера
- [ ] Можно удалить провайдера
- [ ] Можно добавить маршрут с wildcard
- [ ] Можно создать группу с API ключами
- [ ] Tiktoken подсчитывает токены корректно
- [ ] Конфигурация сохраняется в JSON
- [ ] Конфигурация загружается из JSON

### Built-in Providers

1. **OpenAI** - api.openai.com/v1/
2. **Anthropic** - api.anthropic.com/
3. **Google** - Generative Language API
4. **Google Vertex AI** - Vertex AI API
5. **Custom** - Любой совместимый с OpenAI API сервер

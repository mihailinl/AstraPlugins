# Python SDK

Python SDK використовує **декларативний API на основі декораторів**. Наслідуйте `Plugin`, декоруйте методи за допомогою `@tool`, `@action` або `@trigger` — і SDK автоматично побудує метадані можливостей з ваших підказок типів.

Пакет: `astra-plugin-sdk` у `AstraPlugins/astra-plugin-sdk-python`.
Джерело істини: `astra_plugin_sdk/plugin.py` і `astra_plugin_sdk/decorators.py`.

## Встановлення

Потрібен Python 3.10+. Додайте до свого `pyproject.toml`:

```toml
[project]
name = "my_plugin"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "astra-plugin-sdk",
    "grpcio>=1.60.0",
    "protobuf>=4.25.0",
]
```

Демон використовує [`uv`](https://docs.astral.sh/uv/) для встановлення залежностей вашого плагіна в ізольоване віртуальне оточення під час завантаження бандла. Керувати venv вручну не потрібно.

## Мінімальний плагін

```python
from astra_plugin_sdk import Plugin, tool

class MyPlugin(Plugin):
    @tool("Say hello")
    async def greet(self, name: str) -> dict:
        return {"greeting": f"Hello, {name}!"}

if __name__ == "__main__":
    MyPlugin().run()
```

`Plugin.run()` обробляє розбір аргументів CLI (`--daemon-addr`, `--plugin-id`, `--auth-token`), запускає gRPC-сервер на випадковому локальному порту, реєструється в демоні, диспатчить вхідні виклики та обробляє сигнали завершення.

## Декоратори

### `@tool(description)`

Реєструє метод як інструмент AI. Підказки типів автоматично перетворюються на JSON Schema (`decorators.py:28-92`).

```python
from typing import Literal

@tool("Count words in text")
async def word_count(self, text: str) -> dict:
    return {"words": len(text.split())}

@tool("Convert case")
async def convert_case(
    self,
    text: str,
    mode: Literal["upper", "lower", "title"] = "upper",
) -> dict:
    return {"result": getattr(text, mode)()}
```

Підтримувані підказки типів:

| Підказка | JSON Schema |
| --- | --- |
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list[T]` | `{"type": "array", "items": ...}` |
| `dict` | `{"type": "object"}` |
| `Literal["a", "b"]` | `{"type": "string", "enum": ["a", "b"]}` |
| `Optional[T]` | Схема для `T`, поле позначене як не обов'язкове |

Параметри без значень за замовчуванням позначаються як `required`. Повернене значення автоматично обгортається в `{"success": True, "result": ...}`.

### `@action(label, *, icon_svg="", fields=[], ai_available=False, ai_description="", ai_primary_field="")`

Реєструє тип дії Command Graph. Метод викликається, коли команда виконує цю дію.

```python
from astra_plugin_sdk import action, Field

@action(
    "Transform text",
    icon_svg='<svg>…</svg>',
    fields=[
        Field.text("input", "Input text"),
        Field.dropdown("op", "Operation", options=[
            ("upper", "UPPER"), ("lower", "lower"),
        ]),
    ],
    ai_available=True,
    ai_description="Transform a block of text via upper/lower/title case",
    ai_primary_field="input",
)
async def transform_text(self, input: str, op: str):
    return {"success": True, "result": getattr(input, op)()}
```

### `@trigger(label, *, icon_svg="", fields=[])`

Реєструє тип тригера. Декорований метод містить лише метадані — активуйте тригер зі своєї власної фонової роботи через `self.fire_trigger`.

```python
from astra_plugin_sdk import trigger, Field

@trigger("Scheduled time", fields=[
    Field.text("time", "Time", default="09:00", placeholder="HH:MM"),
])
def on_time(self):
    pass

async def tick(self):
    if "on_time" in self.active_triggers:
        await self.fire_trigger("on_time", {"time": "09:00"})
```

## Конструктори `Field`

Усі конструктори — це статичні методи `Field` (`decorators.py:189-319`):

```python
Field.text(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea_with_variables(id, label, ...)
Field.dropdown(id, label, *, options, default="", description="", conditions=[])
Field.number(id, label, *, min=None, max=None, step=None, default="", ...)
Field.toggle(id, label, *, default=False, description="", conditions=[])
```

`dropdown.options` приймає кортежі, словники або прості рядки:

```python
Field.dropdown("mode", "Mode", options=[("fast", "Fast"), ("slow", "Slow")])
Field.dropdown("mode", "Mode", options=[{"value": "fast", "label": "Fast"}])
Field.dropdown("mode", "Mode", options=["fast", "slow"])
```

Умови видимості:

```python
Field.text("custom_value", "Custom value", conditions=[
    Field.condition("mode", "equals", "custom")
])
```

## Хуки життєвого циклу

Перевизначте будь-який з них у своєму підкласі:

| Хук | Призначення |
| --- | --- |
| `async def on_daemon_client_ready(self, client: DaemonClient)` | Викликається після реєстрації для клієнтських плагінів — тримайте `client` для доступу до API демона. |
| `async def on_config_changed(self, config: dict)` | Конфігурацію оновлено (з UI або через `ConfigService.SetConfig`). |
| `async def on_language_changed(self, language: str)` | Змінено мову UI демона — викличте `self.i18n.set_language(language)`. |
| `async def on_active_triggers(self, active_types: list[str])` | Оновлює `self.active_triggers` — використовуйте, щоб не активувати тригери без слухачів. |
| `async def on_shutdown(self)` | Демон запросив завершення — звільніть ресурси тут. |
| `async def health_check(self) -> (bool, str)` | Поверніть `(healthy, status_message)`. |

## Події

```python
def subscribed_events(self) -> list[str]:
    return ["chat_message_sync", "command_completed"]

async def on_chat_sync(self, event):
    # event has id, conversation_id, role, content, source_id,
    # is_streaming, is_complete
    ...

async def on_command_triggered(self, event): ...
async def on_command_completed(self, event): ...
async def on_state_changed(self, event): ...

async def on_event(self, event_type: str, payload: dict):
    # Raw fallback for event types not covered by typed handlers
    ...
```

## Клієнтські плагіни

```python
class MyClientPlugin(Plugin):
    def is_client(self) -> bool:
        return True

    async def on_daemon_client_ready(self, client):
        self.daemon = client
        state = await self.daemon.get_state()
        async for chunk in self.daemon.send_message(conversation_id, "Hello!"):
            print(chunk.text)
```

`DaemonClient` надає `CoreService`, `ChatService`, `VoiceService`, `CommandService`, `ConfigService`, `MediaService` та `MonitorService`. Усі методи — див. `daemon_client.py`.

## Логування

```python
await self.log_info("Processing request")
await self.log_warn("Rate limit near")
await self.log_error("Connection failed")

# Or call HostClient directly:
await self.host.log("info", "Plugin started")
```

Повідомлення логу потрапляють до буфера логів демона і з'являються в UI Plugins.

## Активація тригерів

```python
await self.fire_trigger("on_roll_total", {"total": 42})
```

`fire_trigger` надсилає подію демону, який зіставляє її із зареєстрованими командами. Безпечно викликати за відсутності слухачів, але попередньо перевіряйте `self.active_triggers`, щоб уникнути зайвих RPC.

## i18n

```python
from astra_plugin_sdk import I18n

class MyPlugin(Plugin):
    def __init__(self):
        super().__init__()
        self.i18n = I18n("locales")  # loads locales/*.json

    async def on_language_changed(self, language: str):
        self.i18n.set_language(language)

    @tool("…")
    async def greet(self, name: str):
        return {"msg": self.i18n.tf("greeting", name)}
```

Файли локалізації лежать у `locales/en.json`, `locales/ru.json` тощо. Невідомі ключі відкатуються до англійського файлу, а потім до самого ключа.

## UI contributions

```python
def __init__(self):
    super().__init__()
    self.ui_page("stats", "Stats", "http://localhost:8123/stats.html")
    self.ui_effect("http://localhost:8123/snow.html")
    self.ui_overlay("clock", "http://localhost:8123/clock.html",
                    width=200, height=80)
```

## Робочий приклад — text-utils

Див. `AstraPlugins/examples/text-utils`. Основні моменти:

- Інструменти: `word_count`, `case_convert`, `regex_match`.
- Дія: `transform_text` із `Field.dropdown`.
- Тригер: `on_time` із фоновим циклом asyncio.
- Конфіг: `max_text_length` через `[config].schema` у `plugin.toml`.
- `on_config_changed` оновлює обмеження під час виконання.

Маніфест:

```toml
[plugin]
id = "text-utils"
name = "Text Utils"
version = "0.1.1"

[entry]
command = "python"
args = ["-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
tools = true
actions = true
triggers = true
```

## Куди далі

- [Capabilities](capabilities.md) — повна поведінка кожної можливості.
- [Manifest](manifest.md) — кожне поле `plugin.toml`.
- [Publishing](publishing.md) — збирання, підпис, розповсюдження.

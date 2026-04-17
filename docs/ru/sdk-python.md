# Python SDK

Python SDK использует **декларативный API на основе декораторов**. Наследуйтесь от `Plugin`, помечайте методы декораторами `@tool`, `@action` или `@trigger`, и SDK автоматически соберёт метаданные возможностей из ваших подсказок типов.

Пакет: `astra-plugin-sdk` в `AstraPlugins/astra-plugin-sdk-python`.
Источник правды: `astra_plugin_sdk/plugin.py` и `astra_plugin_sdk/decorators.py`.

## Установка

Требуется Python 3.10+. Добавьте в `pyproject.toml`:

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

Демон использует [`uv`](https://docs.astral.sh/uv/) для установки зависимостей вашего плагина в изолированное виртуальное окружение при загрузке бандла. Вам не нужно управлять venv вручную.

## Минимальный плагин

```python
from astra_plugin_sdk import Plugin, tool

class MyPlugin(Plugin):
    @tool("Say hello")
    async def greet(self, name: str) -> dict:
        return {"greeting": f"Hello, {name}!"}

if __name__ == "__main__":
    MyPlugin().run()
```

`Plugin.run()` выполняет разбор аргументов командной строки (`--daemon-addr`, `--plugin-id`, `--auth-token`), запускает gRPC-сервер на случайном локальном порту, регистрируется у демона, диспетчеризирует входящие вызовы и обрабатывает сигналы завершения.

## Декораторы

### `@tool(description)`

Регистрирует метод как ИИ-инструмент. Подсказки типов автоматически преобразуются в JSON Schema (`decorators.py:28-92`).

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

Поддерживаемые подсказки типов:

| Подсказка | JSON Schema |
| --- | --- |
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list[T]` | `{"type": "array", "items": ...}` |
| `dict` | `{"type": "object"}` |
| `Literal["a", "b"]` | `{"type": "string", "enum": ["a", "b"]}` |
| `Optional[T]` | Схема для `T`, поле помечено как необязательное |

Параметры без значений по умолчанию помечаются как `required`. Возвращаемое значение автоматически оборачивается в `{"success": True, "result": ...}`.

### `@action(label, *, icon_svg="", fields=[], ai_available=False, ai_description="", ai_primary_field="")`

Регистрирует тип действия Графа команд. Метод вызывается, когда команда выполняет это действие.

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

Регистрирует тип триггера. Декорированный метод хранит только метаданные — запускайте триггер из собственной фоновой работы через `self.fire_trigger`.

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

## Билдеры `Field`

Все билдеры — статические методы `Field` (`decorators.py:189-319`):

```python
Field.text(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea(id, label, *, placeholder="", default="", description="", conditions=[])
Field.textarea_with_variables(id, label, ...)
Field.dropdown(id, label, *, options, default="", description="", conditions=[])
Field.number(id, label, *, min=None, max=None, step=None, default="", ...)
Field.toggle(id, label, *, default=False, description="", conditions=[])
```

`dropdown.options` принимает кортежи, словари или простые строки:

```python
Field.dropdown("mode", "Mode", options=[("fast", "Fast"), ("slow", "Slow")])
Field.dropdown("mode", "Mode", options=[{"value": "fast", "label": "Fast"}])
Field.dropdown("mode", "Mode", options=["fast", "slow"])
```

Условия видимости:

```python
Field.text("custom_value", "Custom value", conditions=[
    Field.condition("mode", "equals", "custom")
])
```

## Хуки жизненного цикла

Переопределите любой из них в своём подклассе:

| Хук | Назначение |
| --- | --- |
| `async def on_daemon_client_ready(self, client: DaemonClient)` | Вызывается после регистрации для клиентских плагинов — сохраните `client` для доступа к API демона. |
| `async def on_config_changed(self, config: dict)` | Конфигурация обновлена (через UI или `ConfigService.SetConfig`). |
| `async def on_language_changed(self, language: str)` | Язык UI демона изменился — вызовите `self.i18n.set_language(language)`. |
| `async def on_active_triggers(self, active_types: list[str])` | Обновляет `self.active_triggers` — используйте, чтобы не запускать триггеры, у которых нет слушателей. |
| `async def on_shutdown(self)` | Демон запросил завершение — освободите ресурсы здесь. |
| `async def health_check(self) -> (bool, str)` | Верните `(healthy, status_message)`. |

## События

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

## Клиентские плагины

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

`DaemonClient` предоставляет `CoreService`, `ChatService`, `VoiceService`, `CommandService`, `ConfigService`, `MediaService` и `MonitorService`. См. `daemon_client.py` для всех методов.

## Логирование

```python
await self.log_info("Processing request")
await self.log_warn("Rate limit near")
await self.log_error("Connection failed")

# Or call HostClient directly:
await self.host.log("info", "Plugin started")
```

Сообщения журнала попадают в буфер логов демона и отображаются в UI плагинов.

## Запуск триггеров

```python
await self.fire_trigger("on_roll_total", {"total": 42})
```

`fire_trigger` отправляет событие демону, который сопоставляет его с зарегистрированными командами. Безопасно вызывать, когда слушателей нет, но предварительно проверяйте `self.active_triggers`, чтобы избежать лишних RPC.

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

Файлы локализации находятся в `locales/en.json`, `locales/ru.json` и т. д. Неизвестные ключи откатываются на английский файл, затем на сам ключ.

## UI-контрибуции

```python
def __init__(self):
    super().__init__()
    self.ui_page("stats", "Stats", "http://localhost:8123/stats.html")
    self.ui_effect("http://localhost:8123/snow.html")
    self.ui_overlay("clock", "http://localhost:8123/clock.html",
                    width=200, height=80)
```

## Полный пример — text-utils

См. `AstraPlugins/examples/text-utils`. Ключевые моменты:

- Инструменты: `word_count`, `case_convert`, `regex_match`.
- Действие: `transform_text` с `Field.dropdown`.
- Триггер: `on_time` с фоновым asyncio-циклом.
- Конфигурация: `max_text_length` через `[config].schema` в `plugin.toml`.
- `on_config_changed` обновляет runtime-ограничения.

Манифест:

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

## Куда двигаться дальше

- [Возможности](capabilities.md) — полное поведение каждой возможности.
- [Манифест](manifest.md) — каждое поле `plugin.toml`.
- [Публикация](publishing.md) — сборка, подпись, распространение.

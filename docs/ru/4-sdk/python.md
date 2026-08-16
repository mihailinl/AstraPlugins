# Python SDK

> Перевод. Источник истины — [docs/en](../../en/4-sdk/python.md); при расхождении верна английская версия.

`astra-plugin-sdk` 0.5.0 на PyPI. Наследуйтесь от `Plugin`, декорируйте
методы, запускайте.

<!-- doctest: illustrative reason="a requirements.txt fragment; the scaffold that contains it is what the python-plugin blocks below are executed against" -->
```
astra-plugin-sdk>=0.5,<0.6
grpcio>=1.60.0
grpcio-tools>=1.60.0
protobuf>=4.25.0
```

Python-плагин упаковывается как **`noarch`**: один бандл на все платформы.
Его `[entry]` — это `command = "python"`, `args = ["-m", "src.plugin"]`,
`runtimes = ["python"]`.

## Форма плагина

<!-- doctest: python-plugin -->
```python
"""Timer — an Astra plugin."""

from astra_plugin_sdk import BadArguments, Plugin, TriggerTypeDef, tool


class Timer(Plugin):
    """Start countdowns from chat."""

    @tool("Start a countdown. Use it when the user asks to be reminded in N minutes.")
    async def start_timer(self, minutes: int, label: str = "") -> str:
        # The signature IS the schema. `minutes` is required because it has no
        # default; `label` is optional because it has one; the type hints become
        # the JSON types the model is shown.
        if minutes <= 0:
            raise BadArguments("give me at least a minute")
        await self.log_info(f"timer for {minutes}m")
        await self.fire_trigger("timer_started", {"minutes": minutes, "label": label})
        return f"timer set for {minutes} minutes"

    async def get_trigger_types(self) -> list[TriggerTypeDef]:
        return [TriggerTypeDef(type="timer_started", label="Timer started")]


if __name__ == "__main__":
    Timer().run()


# ── tests ─────────────────────────────────────────────────────────────────────
# Plain `def test_*` functions: the harness is synchronous on purpose, so a
# plugin's test suite needs no pytest-asyncio, no event-loop fixture and no
# "coroutine was never awaited" to decode.

def test_it_starts_a_timer():
    from astra_plugin_sdk.testing import Harness

    with Harness(Timer()).start() as h:
        result = h.call_tool("start_timer", minutes=5)
        assert result.unwrap() == "timer set for 5 minutes"

        fired = h.host.fired_triggers("timer_started")
        assert len(fired) == 1
        assert fired[0].payload["minutes"] == 5


def test_zero_minutes_is_a_bad_argument():
    from astra_plugin_sdk.testing import Harness

    with Harness(Timer()).start() as h:
        result = h.call_tool("start_timer", minutes=0)
        assert not result.success
        assert result.code == "BAD_ARGUMENTS", result.code


def test_the_tool_is_registered_under_the_name_the_daemon_uses():
    from astra_plugin_sdk.testing import Harness

    with Harness(Timer()).start() as h:
        assert h.tool_names() == ["start_timer"]
        h.assert_schema_accepts("start_timer", "minutes", "label")
```

## Декораторы

| | |
|---|---|
| `@tool("description")` | Функция, которую может вызвать модель. Параметры становятся схемой |
| `@action("label")` | Шаг в редакторе команд |
| `@trigger(...)` | Тип триггера |
| `@ui_call` | Метод, который может вызвать собственный UI-iframe плагина |
| `@ui_page` · `@ui_slot` · `@ui_effect` · `@ui_overlay` · `@ui_inject` | Декораторы **класса**. Регистрируют UI-вклад, обслуживаемый из каталога `ui/` бандла или из URL, который отдаёт плагин |
| `Field(...)` | Уточняет схему одного параметра — описание, диапазон, enum |

Всё остальное — переопределение методов `Plugin`: `tts_synthesize`,
`tts_list_voices`, `tts_config_fields`, `stt_transcribe`,
`stt_transcribe_stream`, `stt_get_languages`, `stt_load` / `stt_unload` /
`stt_load_state`, `ai_complete`, `get_action_types`, `execute_action`,
`get_trigger_types`, `get_ui_contributions`, `handle_ui_call`,
`on_config_changed`, `on_language_changed`, `on_active_triggers`,
`on_shutdown`, `health_check`.

## Вызовы наружу, в Astra

Удобные методы `Plugin` — `self.log_info`, `self.log_warn`, `self.log_error`,
`self.fire_trigger(type, payload_dict)`,
`self.push_to_ui(event, payload_dict)` — и всё остальное на `self.host`:

| `self.host.…` | Разрешение |
|---|---|
| `log(level, message)` · `get_config()` · `get_daemon_info()` | нет |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope="session")` | `set_variable` |
| `subscribe_events(types, exclude_source_id="")` | `subscribe_events` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(text, …)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

> **`DaemonClient` сегодня не работает, ни для какого плагина.** Демон
> регистрирует каждый плагин как `ClientType::PluginClient`, и его
> перехватчик авторизации отклоняет эту идентичность на любом пути вне
> `/astra.PluginHostService/` с `permission_denied("plugin session tokens are
> scoped to PluginHostService")` — `client = true` ничего в этом не меняет.
> Так что `submit_user_message`, `subscribe_chat_events`, `speak` и
> `get_settings` все проваливаются во время выполнения. Половина на стороне
> демона не построена, а не сломана.
>
> **`host.send_chat_message` — единственный рабочий способ вести ход ИИ.**

Для случая, когда сторона демона будет достроена: это **`submit_user_message`**,
а не `send_message`, на `DaemonClient`. Полный клиент передаётся в
`on_daemon_client_ready(client)`, и только для плагинов, объявляющих `client
= true` и возвращающих `True` из `is_client()`.

## Куда уходит результат сработавшего триггера

Триггер, который вы зажигаете, пока обрабатываете вызов от Astra, приписывается
этому вызову. Поэтому всё, что он вызовет — запуск команды, произнесённую
реплику, сообщение в чате, — попадёт именно в тот разговор, который человек
сейчас перед собой видит. **Вам для этого писать нечего.** SDK сам переносит
непрозрачную аренду от входящего вызова к исходящему `FireTrigger`:

<!-- doctest: illustrative reason="a method fragment, not a plugin: it needs the enclosing `class(Plugin)` the python-plugin block at the top of this page already executes. The behaviour it claims is executed by tests/test_causality.py, which drives a real plugin over a real socket." -->
```python
@tool("Roll dice")
async def roll_dice(self, count: int = 1):
    results = self.roll(count)
    await self.fire_trigger("on_roll_value", {"value": results[0]})  # attributed
    return f"rolled {results}"
```

Триггер, зажжённый откуда-либо ещё, — это **корневое событие**: демон подошьёт
его к собственной ветке автоматизации этого плагина, вместо того чтобы гадать о
разговоре. Сюда попадают фоновая задача, запущенная в `on_start`, таймер,
обратный вызов из расширения на C и всё, что живёт в созданном вами потоке. Это
верный ответ, а не ухудшенный: не тот разговор хуже, чем никакой.

Механизм — `contextvars.ContextVar`, поэтому он следует за `await`,
`asyncio.create_task` и `asyncio.gather`. **`loop.run_in_executor` контекст не
копирует**, так что работа, отданная в пул потоков, теряет привязку:

<!-- doctest: illustrative reason="three lines out of the middle of a coroutine; there is no `loop` or `work` here to bind. The workaround is executed by test_a_context_copied_across_the_executor_carries_the_cause, so this cannot become a rumour." -->
```python
loop = asyncio.get_running_loop()
ctx = contextvars.copy_context()
await loop.run_in_executor(None, lambda: ctx.run(work))   # keeps it
```

Зажигайте из корутины там, где можете; переносите контекст туда, где не можете.

Всё это проверяется вашими же тестами: у корневого события
`FiredTrigger.caused_by` равен `None`, а `WireHarness.lease("...")` выдаёт вызов
так же, как это сделает демон.

## Ошибки

Бросайте их; SDK отображает их на те же коды провода, что и два других SDK.

`BadArguments` · `NotFound` · `NotConfigured` · `Unauthorized` · `RateLimited`
· `Unavailable` · `Timeout` · `InternalError`, все — подклассы `PluginError`,
с `ErrorCode` как перечислением. См.
[`reference/errors.md`](../reference/errors.md).

## Типы возможностей — это dataclasses

`ToolDef`, `VoiceInfo`, `AiModelInfo`, `FieldDef`, `DropdownOption`,
`FieldCondition`, `ActionTypeDef`, `TriggerTypeDef`, `UiContribution`.

Возврат обычного `dict` там, где ожидается dataclass, всё ещё работает и
выдаёт `DeprecationWarning`: устарело в 0.5.0, будет удалено в 0.7.0. Ловите
это в CI через `python -W error::DeprecationWarning`.

## Тестирование

| | |
|---|---|
| `testing.Harness` | Плагин в этом же процессе, через настоящий сервисёр возможностей |
| `testing.WireHarness` | Плагин как процесс, по gRPC |
| `testing.RecordingHost` | Что ваш плагин сообщил Astra: `fired_triggers()`, `logs()`, `variables()`, `ui_pushes()`, `chat_messages()`, плюс `fail_next` / `fail_always` |
| Фикстуры pytest | `astra_harness` и `astra_wire`, если вы используете pytest |

`h.call_tool("name", **args)` принимает имя инструмента **позиционно** — `/`
в сигнатуре несущий, потому что инструмент, у которого собственный параметр
называется `name`, иначе был бы невызываемым.

Harness вызывает настоящий сервисёр, так что покрывает то, что не покрывает
прямой вызов метода: что инструмент зарегистрирован под именем, которое
использует демон, что его схема разбирается, что аргументы переживают
`json.dumps` → `json.loads`, что возвращаемое значение сериализуется, и что
брошенная ошибка становится кодом, по которому действует демон.

## Чего этот SDK пока не умеет

- **`DaemonClient` нефункционален.** Демон ограничивает токен сессии каждого
  плагина `PluginHostService`, так что каждый сервис на стороне демона
  отвечает `permission_denied` — включая плагины с `client = true`.
  Используйте `host.send_chat_message`.
- **Нет собственного `stdout`.** SDK переключает stdout на построчную
  буферизацию, потому что супервизор демона читает его, чтобы понять, что
  плагин жив; блочная буферизация приводила к тому, что супервизор убивал
  процесс по тайм-ауту старта. Используйте мост логирования
  (`install_logging_bridge`), а не `print`.
- **Старт медленнее, чем у двух других SDK** — интерпретатор плюс импорт
  `grpcio`. Бюджет демона — 20 с до первой строки вывода, это щедро, но
  плагин, импортирующий большой ML-стек на уровне модуля, может в него не
  уложиться. Импортируйте лениво, в том хуке, которому это нужно.
- **`ai_get_models` устарел** (0.5.0, форма с dict удаляема в 0.7.0; сам хук
  выводится из обращения в 0.8), и его никто не вызывает.
- **`tts_synthesize_stream` привязан, но не маршрутизирован** — точки вызова
  у демона нет.
- **Python SDK опубликован в версии 0.5.0**, так что свежая заготовка
  разрешается с PyPI (проверено против
  `https://pypi.org/pypi/astra-plugin-sdk/json`). Берите 0.5.0 или новее: это
  первый релиз, прикрепляющий `x-session-token`, который демон требует на
  каждом RPC хоста, кроме `Register`, а на всё более старое демон отвечает
  `unauthenticated` на каждой строке лога и каждом вызове хоста.

## См. также

[Таблица хуков для Python](../hooks/python.md) ·
[паритет](../reference/parity.md) · [ошибки](../reference/errors.md) ·
[версионирование](../versioning.md)

# Python SDK

> Переклад. Джерело істини — [docs/en](../../en/4-sdk/python.md); за розбіжності відповідає англійська версія.

`astra-plugin-sdk` 0.5.0 на PyPI. Успадковуйтесь від `Plugin`, декоруйте
методи, запускайте.

<!-- doctest: illustrative reason="a requirements.txt fragment; the scaffold that contains it is what the python-plugin blocks below are executed against" -->
```
astra-plugin-sdk>=0.5,<0.6
grpcio>=1.60.0
grpcio-tools>=1.60.0
protobuf>=4.25.0
```

Python-плагін пакується як **`noarch`**: один бандл на всі платформи. Його
`[entry]` — це `command = "python"`, `args = ["-m", "src.plugin"]`,
`runtimes = ["python"]`.

## Форма плагіна

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

## Декоратори

| | |
|---|---|
| `@tool("description")` | Функція, яку може викликати модель. Параметри стають схемою |
| `@action("label")` | Крок у редакторі команд |
| `@trigger(...)` | Тип тригера |
| `@ui_call` | Метод, який може викликати власний UI-iframe плагіна |
| `@ui_page` · `@ui_slot` · `@ui_effect` · `@ui_overlay` · `@ui_inject` | Декоратори **класу**. Реєструють UI-внесок, що обслуговується з каталогу `ui/` бандла або з URL, який віддає плагін |
| `Field(...)` | Уточнює схему одного параметра — опис, діапазон, enum |

Усе інше — перевизначення методів `Plugin`: `tts_synthesize`,
`tts_list_voices`, `tts_config_fields`, `stt_transcribe`,
`stt_transcribe_stream`, `stt_get_languages`, `stt_load` / `stt_unload` /
`stt_load_state`, `ai_complete`, `get_action_types`, `execute_action`,
`get_trigger_types`, `get_ui_contributions`, `handle_ui_call`,
`on_config_changed`, `on_language_changed`, `on_active_triggers`,
`on_shutdown`, `health_check`.

## Виклики назовні, в Astra

Зручні методи `Plugin` — `self.log_info`, `self.log_warn`, `self.log_error`,
`self.fire_trigger(type, payload_dict)`,
`self.push_to_ui(event, payload_dict)` — і все інше на `self.host`:

| `self.host.…` | Дозвіл |
|---|---|
| `log(level, message)` · `get_config()` · `get_daemon_info()` | немає |
| `fire_trigger(type, payload_json)` | `fire_trigger` |
| `set_variable(name, value, scope="session")` | `set_variable` |
| `subscribe_events(types, exclude_source_id="")` | `subscribe_events` |
| `push_to_ui(event, payload_json)` | `push_to_ui` |
| `send_chat_message(text, …)` | `send_chat_message` |
| `set_theme_contribution(theme)` | `set_theme_contribution` |

> **`DaemonClient` сьогодні не працює, для жодного плагіна.** Демон реєструє
> кожен плагін як `ClientType::PluginClient`, і його перехоплювач
> авторизації відхиляє цю ідентичність на будь-якому шляху поза
> `/astra.PluginHostService/` з `permission_denied("plugin session tokens are
> scoped to PluginHostService")` — `client = true` нічого в цьому не міняє.
> Тож `submit_user_message`, `subscribe_chat_events`, `speak` і
> `get_settings` усі провалюються під час виконання. Половина на боці демона
> не побудована, а не зламана.
>
> **`host.send_chat_message` — єдиний робочий спосіб вести хід ШІ.**

Для випадку, коли сторона демона буде добудована: це
**`submit_user_message`**, а не `send_message`, на `DaemonClient`. Повний
клієнт передається в `on_daemon_client_ready(client)`, і лише для плагінів,
що оголошують `client = true` і повертають `True` з `is_client()`.

## Куди потрапляє результат спрацьованого тригера

Тригер, який ви запалюєте, поки обробляєте виклик від Astra, приписується цьому
викликові. Тому все, що він спричинить — запуск команди, вимовлену репліку,
повідомлення в чаті, — потрапить саме в ту розмову, яку людина зараз бачить
перед собою. **Вам для цього писати нічого не треба.** SDK сам переносить
непрозору оренду від вхідного виклику до вихідного `FireTrigger`:

<!-- doctest: illustrative reason="a method fragment, not a plugin: it needs the enclosing `class(Plugin)` the python-plugin block at the top of this page already executes. The behaviour it claims is executed by tests/test_causality.py, which drives a real plugin over a real socket." -->
```python
@tool("Roll dice")
async def roll_dice(self, count: int = 1):
    results = self.roll(count)
    await self.fire_trigger("on_roll_value", {"value": results[0]})  # attributed
    return f"rolled {results}"
```

Тригер, запалений будь-де ще, — це **кореневa подія**: демон підошиє її до
власної гілки автоматизації цього плагіна, замість того щоб вгадувати розмову.
Сюди належать фонове завдання, запущене в `on_start`, таймер, зворотний виклик з
розширення на C і все, що живе в створеному вами потоці. Це правильна відповідь,
а не погіршена: не та розмова гірша за жодну.

Механізм — `contextvars.ContextVar`, тож він іде слідом за `await`,
`asyncio.create_task` і `asyncio.gather`. **`loop.run_in_executor` контекст не
копіює**, тому робота, віддана в пул потоків, втрачає прив'язку:

<!-- doctest: illustrative reason="three lines out of the middle of a coroutine; there is no `loop` or `work` here to bind. The workaround is executed by test_a_context_copied_across_the_executor_carries_the_cause, so this cannot become a rumour." -->
```python
loop = asyncio.get_running_loop()
ctx = contextvars.copy_context()
await loop.run_in_executor(None, lambda: ctx.run(work))   # keeps it
```

Запалюйте з корутини там, де можете; переносьте контекст туди, де не можете.

Усе це перевіряється вашими ж тестами: у кореневої події
`FiredTrigger.caused_by` дорівнює `None`, а `WireHarness.lease("...")` видає
виклик так само, як це зробить демон.

## Помилки

Кидайте їх; SDK відображає їх на ті самі коди дроту, що й два інші SDK.

`BadArguments` · `NotFound` · `NotConfigured` · `Unauthorized` · `RateLimited`
· `Unavailable` · `Timeout` · `InternalError`, усі — підкласи `PluginError`, з
`ErrorCode` як переліком. Див. [`reference/errors.md`](../reference/errors.md).

## Типи можливостей — це dataclasses

`ToolDef`, `VoiceInfo`, `AiModelInfo`, `FieldDef`, `DropdownOption`,
`FieldCondition`, `ActionTypeDef`, `TriggerTypeDef`, `UiContribution`.

Повернення звичайного `dict` там, де очікується dataclass, все ще працює і
видає `DeprecationWarning`: застаріло в 0.5.0, буде видалено в 0.7.0. Ловіть
це в CI через `python -W error::DeprecationWarning`.

## Тестування

| | |
|---|---|
| `testing.Harness` | Плагін у цьому ж процесі, через справжній сервісер можливостей |
| `testing.WireHarness` | Плагін як процес, по gRPC |
| `testing.RecordingHost` | Що ваш плагін повідомив Astra: `fired_triggers()`, `logs()`, `variables()`, `ui_pushes()`, `chat_messages()`, плюс `fail_next` / `fail_always` |
| Фікстури pytest | `astra_harness` і `astra_wire`, якщо ви використовуєте pytest |

`h.call_tool("name", **args)` приймає ім'я інструмента **позиційно** — `/` у
сигнатурі несучий, тому що інструмент, у якого власний параметр зветься
`name`, інакше був би невикличним.

Harness викликає справжній сервісер, тож покриває те, чого не покриває
прямий виклик методу: що інструмент зареєстрований під ім'ям, яке
використовує демон, що його схема розбирається, що аргументи переживають
`json.dumps` → `json.loads`, що значення, яке повертається, серіалізується, і
що кинута помилка стає кодом, за яким діє демон.

## Чого цей SDK поки не вміє

- **`DaemonClient` нефункціональний.** Демон обмежує токен сесії кожного
  плагіна `PluginHostService`, тож кожен сервіс на боці демона відповідає
  `permission_denied` — включно з плагінами з `client = true`. Використовуйте
  `host.send_chat_message`.
- **Немає власного `stdout`.** SDK перемикає stdout на порядкову буферизацію,
  тому що супервізор демона читає його, щоб зрозуміти, що плагін живий;
  блочна буферизація призводила до того, що супервізор вбивав процес за
  тайм-аутом старту. Використовуйте міст логування
  (`install_logging_bridge`), а не `print`.
- **Старт повільніший, ніж у двох інших SDK** — інтерпретатор плюс імпорт
  `grpcio`. Бюджет демона — 20 с до першого рядка виводу, це щедро, але
  плагін, що імпортує великий ML-стек на рівні модуля, може в нього не
  вкластися. Імпортуйте ліниво, у тому хуці, якому це потрібно.
- **`ai_get_models` застарів** (0.5.0, форму з dict видаляється у 0.7.0; сам
  хук виводиться з обігу в 0.8), і його ніхто не викликає.
- **`tts_synthesize_stream` прив'язаний, але не маршрутизований** — точки
  виклику в демона немає.
- **Python SDK опублікований у версії 0.5.0**, тож свіжа заготовка
  розв'язується з PyPI (перевірено проти
  `https://pypi.org/pypi/astra-plugin-sdk/json`). Беріть 0.5.0 або новіший:
  це перший реліз, що прикріплює `x-session-token`, який демон вимагає на
  кожному RPC хоста, крім `Register`, а на все старіше демон відповідає
  `unauthenticated` на кожному рядку логу і кожному виклику хоста.

## Див. також

[Таблиця хуків для Python](../hooks/python.md) ·
[паритет](../reference/parity.md) · [помилки](../reference/errors.md) ·
[версіонування](../versioning.md)

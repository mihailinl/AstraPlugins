# Довідник `plugin.toml`

Кожен плагін декларує себе у маніфесті `plugin.toml` в корені свого проєкту. Цей файл повідомляє демону, як запускати плагін, які можливості він реалізує та яку конфігурацію приймає.

## Повний приклад

```toml
[plugin]
id = "text-utils"
name = "Text Utils"
version = "0.1.1"
description = "Word count, case conversion, regex matching"
author = "Astra Team"
license = "MIT"

[entry]
command = "python"
args = ["-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
tools = true
actions = true
triggers = true
tts = false
stt = false
ai_provider = false
client = false
ui_contributions = false
event_handlers = false

[config]
schema = """
{
  "type": "object",
  "properties": {
    "max_text_length": {
      "type": "number",
      "default": 10000,
      "title": "Max Text Length"
    }
  }
}
"""
```

## `[plugin]` — метадані

| Поле | Тип | Обов'язкове | Опис |
| --- | --- | --- | --- |
| `id` | рядок | так | Нижній регістр, лише літери, цифри та дефіси. Унікально ідентифікує плагін. |
| `name` | рядок | так | Відображувана назва у UI Plugins. |
| `version` | рядок | так | Семантична версія (`X.Y.Z`). Використовується для виявлення оновлень. |
| `description` | рядок | рекомендовано | Короткий опис. Показується у UI Plugins. |
| `author` | рядок | рекомендовано | Ім'я автора або назва організації. |
| `license` | рядок | рекомендовано | SPDX-ідентифікатор ліцензії (`MIT`, `Apache-2.0`, …). |

## `[entry]` — як запустити плагін

| Поле | Тип | Обов'язкове | Опис |
| --- | --- | --- | --- |
| `command` | рядок | так | Виконуваний файл для запуску. Для Rust — шлях до скомпільованого бінарника; для Python — `"python"`; для TypeScript — `"node"`. |
| `args` | масив рядків | ні | Аргументи, що додаються перед `--daemon-addr`, `--plugin-id`, `--auth-token`. Типові значення: `["-m", "src.plugin"]` для Python або `["dist/index.js"]` для Node. |
| `runtimes` | масив рядків | ні | Підказка демону. Підтримуються: `"python"`, `"node"`, `"rust"`. Плагіни на Python/Node мають завжди встановлювати це, щоб демон міг підготувати рантайм (наприклад, створити `uv` venv для Python). |

Демон додає `--daemon-addr <addr> --plugin-id <id>` при кожному запуску і, за потреби, `--auth-token <token>` для клієнтських плагінів.

## `[capabilities]` — що реалізує плагін

Кожне поле — булеве зі значенням `false` за замовчуванням. Встановлюйте `true` лише для тих можливостей, які ваш код справді обробляє — демон використовує це для розподілу ресурсів та рішення, чи виводити плагін у відповідному UI (наприклад, додати його голоси до вибору TTS).

| Можливість | Призначення |
| --- | --- |
| `tools` | Інструменти AI, які може викликати чат-модель. |
| `tts` | Постачальник голосів для синтезу мовлення. |
| `stt` | Постачальник мов для розпізнавання мовлення. |
| `ai_provider` | Альтернативний бекенд AI-генерації. |
| `actions` | Власні типи дій у Command Graph. |
| `triggers` | Власні типи тригерів у Command Graph. |
| `client` | Повноцінний клієнт демона (потрібен токен сесії). |
| `ui_contributions` | Сторінки UI, оверлеї, ефекти, ін'єкції у слоти. |
| `event_handlers` | Підписка на потік подій демона. |

Повну поведінку кожної можливості — див. у [Capabilities](capabilities.md).

## `[config]` — налаштування для користувача

```toml
[config]
schema = """
{
  "type": "object",
  "properties": {
    "api_key": {
      "type": "string",
      "title": "API Key",
      "description": "Token for the remote service",
      "x-secret": true
    },
    "timeout_ms": {
      "type": "number",
      "default": 5000,
      "minimum": 100,
      "maximum": 60000,
      "title": "Timeout (ms)"
    },
    "mode": {
      "type": "string",
      "enum": ["fast", "accurate"],
      "default": "fast",
      "title": "Mode"
    }
  },
  "required": ["api_key"]
}
"""
```

Правила:

- `schema` — це **рядок JSON Schema**. Корінь має мати `"type": "object"`.
- Демон рендерить схему як форму на сторінці налаштувань плагіна.
- `title` визначає мітку поля; `description` показується як підказка.
- `default` задає початкове значення.
- `x-secret: true` маскує значення в UI і зберігає його в зашифрованому вигляді.
- `enum` рендериться як випадний список.
- Масив `required` позначає обов'язкові поля.
- Коли користувач оновлює налаштування, демон викликає `OnConfigChanged` з новим JSON-блобом.

## TOML-поля поза схемою

Плагіни можуть додавати довільні розділи верхнього рівня, які демон ігнорує — зручно для інструментарію. CLI попереджає про невідомі поля, але не відхиляє їх.

## Локалізація маніфесту

Ви можете включати файли `locales/<lang>.json` у бандл плагіна, щоб перекладати текст, видимий користувачу (`name`, `description`, мітки дій, мітки полів тощо). Використовуйте хелпер `I18n` у кожному SDK, щоб читати їх із коду. Локалізується лише **текст** маніфесту — ключі, ID та значення enum залишаються сталими.

## Перевірка маніфесту

```bash
astra-plugin validate
```

Перевіряє:

- Наявність обов'язкових полів (`plugin.id`, `plugin.name`, `plugin.version`, `entry.command`).
- `plugin.id` відповідає шаблону "нижній регістр + літери/цифри + дефіси".
- `plugin.version` відповідає SemVer (`X.Y.Z`).
- Увімкнено хоча б одну можливість.
- `[config].schema` парситься як JSON і має `"type": "object"` на кореневому рівні.
- Наявність метаданих (description, author).

Див. [CLI reference → validate](cli.md#astra-plugin-validate).

# Дозволи

> Переклад. Джерело істини — [docs/en](../../en/3-reference/permissions.md); за розбіжності відповідає англійська версія.

Що дає кожен id з `[permissions]`, чого це коштує користувачу, і як написати
`reason`, який варто читати.

Це сторінка для авторів. Нормативні правила — видачі, стелі,
`permissions_hash`, точна семантика відмови — в
[`spec/permissions.md`](../spec/permissions.md). Згенерована таблиця того,
який RPC закриває кожен id, — в [`reference/manifest.md`](../reference/manifest.md)
і [`reference/parity.md`](../reference/parity.md), обидві виведені з
`spec/hooks.yaml` і звірені з власною таблицею демона правилом паритету R6.

## Форма цього

`[capabilities]` каже, що демон може викликати **всередині** вашого плагіна.
`[permissions]` каже, які RPC хоста ваш плагін може викликати **назовні**.
Два питання, два розділи; можливість ніколи не передбачає дозвіл.

Три властивості, кожна з яких когось та здивує:

1. **За замовчуванням усе заборонено.** Відсутність розділу `[permissions]`
   означає відсутність RPC хоста понад стартову четвірку.
2. **Оголосити — означає попросити, а не отримати.** Ваш маніфест — це
   запит. Виданий набір обчислює демон, виходячи з того, звідки плагін
   з'явився, і для встановленого чи імпортованого плагіна зберігає його там,
   куди плагін не може писати, — сам маніфест лежить у каталозі плагіна,
   який плагін може редагувати. **Сайдлоадинг це перевертає**: для каталогу з
   вихідним кодом у режимі розробника маніфест *і є* видача, що
   перечитується при кожному завантаженні, без стелі. Саме це робить робочим
   цикл розробки, і саме тому сайдлоадинг — інструмент розробника, а не шлях
   встановлення.
3. **Невідомий id зберігається і залишається бездіяльним.** Нові id
   виходять разом з новими версіями Astra, тож старіший демон зберігає ключ,
   якого не розпізнає, замість того щоб відхилити ваш маніфест. Він нічого
   не дає. `astra-plugin check` попереджає — одруківку неможливо відрізнити
   від прямо сумісного id на етапі розбору, тому це попередження, а не
   помилка, а `--strict` перетворює його на неуспішний вихід:

   <!-- doctest: output from="astra-plugin check --strict ." unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
   ```
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client
     FAILED: 1 warning(s), and --strict treats warnings as errors
   ```

   Аркуш згоди на встановлення в Astra показує той самий id під власною
   міткою `permission.unrecognised`, тож він не губиться мовчки і на вході
   теж.

## Чотири виклики, яким нічого не потрібно

| RPC | Чому безкоштовний |
|---|---|
| `Register` | Рукостискання. Плагіна ще немає, щоб у нього були дозволи |
| `PluginLog` | Запис у власний лог |
| `GetPluginSelfConfig` | Читання власних налаштувань |
| `GetDaemonInfo` | `version`, `state`, `grpc_port`, `language` — усе це вже було у відповіді на реєстрацію |

Те, що `GetDaemonInfo` безкоштовний, — рішення, а не недогляд: чекбокс, який
нічого не захищає, — це те, як користувачі звикають ставити галочки не
дивлячись.

## Вісім id

| Id | Закриває | Свій чекбокс | Відхиляється для локального імпорту | Що дозволяє |
|---|---|---|---|---|
| `fire_trigger` | `FireTrigger` | ні | ні | Запускати збережені автоматизації користувача |
| `subscribe_events` | `SubscribeEvents` | ні | ні | Отримувати події демона — **бере список дозволених `types`** |
| `set_variable` | `SetVariable` | ні | ні | Писати в контекст змінних демона, у власному просторі імен |
| `send_chat_message` | `SendChatMessage` | **так** | **так** | Керувати ходом ШІ, наче говорив сам користувач |
| `push_to_ui` | `PushToUi` | **так** | ні | Надсилати подію у свої власні панелі |
| `set_theme_contribution` | `SetThemeContribution` | **так** | **так** | Переоформити весь застосунок |
| `dom_access` | — (поверхня) | **так** | **так** | Виконувати свій код всередині вікна Astra, з доступом до бесід та інтерфейсу будь-якого іншого плагіна |
| `client` | — (поверхня) | **так** | **так** | Бути фронтендом чату з власною сесією |

`dom_access` і `client` не закривають жоден RPC, і в цьому суть: це
**поверхні**. `dom_access` визначає, чи рендериться UI-внесок як скрипт у
вікні Astra, чи як ізольований iframe; `client` — це стеля того, чим плагін
взагалі може бути. Їх відхиляють там, де видається сама поверхня, а не на
шлюзі виклику.

`dom_access` додатково отримує другий екран згоди. Якщо ви тягнетеся за
ним, спершу прочитайте [модель безпеки](../1-orientation/security.md) і
переконайтеся, що `push_to_ui` у власну панель не вирішить задачу.

## Аргументи

Два id приймають аргументи, і обидва звужують те, що ви отримуєте.

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "meeting-notes"
name = "Meeting Notes"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/meeting_notes"

[capabilities]
tools = true
event_handlers = true

[permissions]
subscribe_events = { types = ["command_completed", "state_changed"], reason = "Notices when a recording command finishes so it can write the summary" }
set_variable = { scopes = ["plugin"], reason = "Stores the id of the note it just wrote so your commands can open it" }
fire_trigger = { reason = "Fires meeting_summarised when a summary is ready" }
```

- **`subscribe_events.types` — це список дозволених, який застосовує демон**
  — а не фільтр, який надсилає ваш плагін. Без нього кожен підписник
  отримував кожну подію, включно з `speech_recognized`, яка несе
  транскрипти користувача. Порожній список не дозволяє нічого.
- **`set_variable.scopes`** — це `"plugin"`, `"session"` або `"persistent"`.

## Як написати reason

`reason` рендериться під власною міткою Astra для дозволу, візуально
підпорядковано, в лапках, простим текстом, з обмеженням у 140 символів, і
завжди з префіксом *«The author says:»*. Мітка належить Astra, мовою
користувача; reason — ваш. Ви не можете сформувати саму мітку, і це навмисно:
формулювання фіксуються в постачанні Astra і не повинні бути записуваними
через лістинг.

Хороший reason:

- **називає фічу, яку впізнає користувач**, а не API — *«Запускає тригер
  on_dice_roll, який ви налаштували»*, а не *«викликає FireTrigger»*;
- **каже коли**, якщо не завжди — *«лише поки триває запис»*;
- **не повторює мітку.** Astra вже її відрендерила;
- **не тисне.** Жодної терміновості, погроз, інструкцій користувачу. Аркуш
  згоди — останнє місце для винятку, і текст з bidi-перевизначеннями або
  з'єднувачами нульової ширини відхиляється там, де відображається дослівно.

| Замість | Пишіть |
|---|---|
| `"needs fire_trigger"` | `"Fires the trigger you configure when a roll completes"` |
| `"required for the plugin to work"` | `"Reads command-completion events so it can log the run"` |
| `"full access to the UI"` | `"Draws the timer in the panel this plugin adds to the sidebar"` |
| `"REQUIRED! Do not disable!"` | — вилучіть дозвіл, або скажіть, для чого він |

Дозвіл без правдоподібного reason — це дозвіл, який треба видалити з
маніфесту. Автоматично це ніхто не перевіряє; єдиний захист — людина, що
читає вашу заявку, і `astra-plugin check` скаже вам, коли ви оголосили
дозвіл, який не потрібен вашим можливостям.

## Що відбувається, коли дозволу бракує

Виклик повертається з `permission_denied`, з повідомленням, що називає
дозвіл **і** звідки взявся виданий набір. У тесті це можна інсценувати рівно
так:

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Notifier;

#[astra::plugin]
impl Notifier {
    /// Announce that something happened.
    #[tool]
    async fn announce(&self, ctx: &PluginContext) -> Result<String, ToolError> {
        // Handle the denial rather than propagating it: a tool that returns an
        // error the model cannot act on is worse than one that says what it did.
        match ctx.host().fire_trigger("announced", "{}").await {
            Ok(()) => Ok("announced".into()),
            // `{e:#}` and not `{e}`: the host call fails with a short outer
            // message and the useful half — the permission id and where the
            // granted set came from — is in the cause chain.
            Err(e) => Ok(format!("could not fire the trigger: {e:#}")),
        }
    }
}

astra::main!(Notifier::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn a_missing_grant_is_reported_not_hidden() {
        let h = Harness::new(Notifier::default()).start().await.unwrap();
        h.host().deny("fire_trigger");

        let answer = h.call_tool("announce", json!({})).await.unwrap();
        assert!(answer.contains("fire_trigger"), "{answer}");
    }
}
```

`astra-plugin doctor` відповідає на те саме питання про маніфест ще до того,
як ви його хоч раз запустите:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## Звідки береться виданий набір

| Шлях встановлення | Видано |
|---|---|
| З каталогу, верифікований | те, що запросив маніфест, після згоди |
| Файл `.astraplugin`, імпортований вручну | маніфест, **зі стелею**: `send_chat_message`, `set_theme_contribution`, `dom_access`, `client` відхиляються безумовно |
| Сайдлоаднутий каталог з вихідним кодом, режим розробника увімкнено | маніфест, без стелі |
| `Untrusted` / `TamperDetected` / `Revoked` | нічого |
| Встановлено до появи записів довіри | маніфест, зі стелею як у імпортованого файлу |

Повна таблиця і обґрунтування:
[`spec/permissions.md` §4](../spec/permissions.md).

## Згода, з боку користувача

Дозволи згруповані за ризиком. П'ять високоризикових отримують кожен свій
чекбокс, і кнопка «Встановити» лишається неактивною, поки не позначено
кожен; `dom_access` отримує другий екран. Навмисно **немає введення-для-
підтвердження**: це патерн для незворотного знищення, а привчання
користувачів друкувати, щоб пройти його, знищує сигнал, який несе чекбокс.

При оновленні: дозволи, що не змінилися або звузилися, застосовуються
мовчки; дозволи, що **розширилися**, ставлять оновлення в чергу без
встановлення і лишають стару версію працюючою, поки користувач не розгляне
різницю. Відмова нічого не коштує.

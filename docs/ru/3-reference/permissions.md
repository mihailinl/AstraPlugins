# Разрешения

> Перевод. Источник истины — [docs/en](../../en/3-reference/permissions.md); при расхождении верна английская версия.

Что даёт каждый id из `[permissions]`, чего это стоит пользователю, и как
написать `reason`, который стоит читать.

Это страница для авторов. Нормативные правила — выдачи, потолки,
`permissions_hash`, точная семантика отказа — в
[`spec/permissions.md`](../spec/permissions.md). Сгенерированная таблица
того, какой RPC закрывает каждый id, — в
[`reference/manifest.md`](../reference/manifest.md) и
[`reference/parity.md`](../reference/parity.md), обе выведены из
`spec/hooks.yaml` и сверены с собственной таблицей демона правилом паритета
R6.

## Форма этого

`[capabilities]` говорит, что демон может вызвать **внутри** вашего плагина.
`[permissions]` говорит, какие RPC хоста ваш плагин может вызывать
**наружу**. Два вопроса, два раздела; возможность никогда не подразумевает
разрешение.

Три свойства, каждое из которых кого-нибудь да удивит:

1. **По умолчанию всё запрещено.** Отсутствие раздела `[permissions]`
   означает отсутствие RPC хоста сверх стартовой четвёрки.
2. **Объявить — значит попросить, а не получить.** Ваш манифест — это запрос.
   Выданный набор вычисляет демон, исходя из того, откуда плагин взялся, и
   для установленного или импортированного плагина хранит его там, куда
   плагин не может писать, — сам манифест лежит в каталоге плагина, который
   плагин может редактировать. **Сайдлоадинг это переворачивает**: для
   каталога с исходниками в режиме разработчика манифест *и есть* выдача,
   перечитываемая при каждой загрузке, без потолка. Именно это делает
   рабочим цикл разработки, и именно поэтому сайдлоадинг — инструмент
   разработчика, а не путь установки.
3. **Неизвестный id сохраняется и остаётся бездействующим.** Новые id
   выходят вместе с новыми версиями Astra, так что более старый демон
   сохраняет ключ, который не распознаёт, вместо того чтобы отклонить ваш
   манифест. Он ничего не даёт. `astra-plugin check` предупреждает — опечатку
   невозможно отличить от прямо совместимого id на этапе разбора, поэтому это
   предупреждение, а не ошибка, а `--strict` превращает его в неуспешный
   выход:

   <!-- doctest: output from="astra-plugin check --strict ." -->
   ```
     WARN: Unknown permission 'read_the_users_mail'. This Astra grants nothing for it. Valid: fire_trigger, subscribe_events, set_variable, send_chat_message, push_to_ui, set_theme_contribution, dom_access, client
     FAILED: 1 warning(s), and --strict treats warnings as errors
   ```

   Лист согласия на установку в Astra показывает тот же id под собственной
   меткой `permission.unrecognised`, так что он не теряется молча и на входе
   тоже.

## Четыре вызова, которым ничего не нужно

| RPC | Почему бесплатен |
|---|---|
| `Register` | Рукопожатие. Плагина ещё нет, чтобы у него были разрешения |
| `PluginLog` | Запись в собственный лог |
| `GetPluginSelfConfig` | Чтение собственных настроек |
| `GetDaemonInfo` | `version`, `state`, `grpc_port`, `language` — всё это уже было в ответе на регистрацию |

То, что `GetDaemonInfo` бесплатен, — решение, а не недосмотр: чекбокс,
который ничего не защищает, — это то, как пользователи привыкают их тикать
не глядя.

## Восемь id

| Id | Закрывает | Свой чекбокс | Отклоняется для локального импорта | Что позволяет |
|---|---|---|---|---|
| `fire_trigger` | `FireTrigger` | нет | нет | Запускать сохранённые автоматизации пользователя |
| `subscribe_events` | `SubscribeEvents` | нет | нет | Получать события демона — **берёт список разрешённых `types`** |
| `set_variable` | `SetVariable` | нет | нет | Писать в контекст переменных демона, в собственном пространстве имён |
| `send_chat_message` | `SendChatMessage` | **да** | **да** | Управлять ходом ИИ, как будто говорил сам пользователь |
| `push_to_ui` | `PushToUi` | **да** | нет | Отправлять событие в свои собственные панели |
| `set_theme_contribution` | `SetThemeContribution` | **да** | **да** | Переоформить всё приложение |
| `dom_access` | — (поверхность) | **да** | **да** | Выполнять свой код внутри окна Astra, с доступом к беседам и интерфейсу любого другого плагина |
| `client` | — (поверхность) | **да** | **да** | Быть фронтендом чата с собственной сессией |

`dom_access` и `client` не закрывают ни один RPC, и в этом суть: это
**поверхности**. `dom_access` определяет, отрисовывается ли UI-вклад как
скрипт в окне Astra или как изолированный iframe; `client` — это потолок
того, чем плагин вообще может быть. Их отклоняют там, где выдаётся сама
поверхность, а не на шлюзе вызова.

`dom_access` дополнительно получает второй экран согласия. Если вы тянетесь
за ним, сначала прочтите [модель безопасности](../1-orientation/security.md)
и убедитесь, что `push_to_ui` в собственную панель не решит задачу.

## Аргументы

Два id принимают аргументы, и оба сужают то, что вы получаете.

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

- **`subscribe_events.types` — это список разрешённых, применяемый демоном**
  — а не фильтром, который отправляет ваш плагин. Без него каждый подписчик
  получал каждое событие, включая `speech_recognized`, которое несёт
  транскрипты пользователя. Пустой список не разрешает ничего.
- **`set_variable.scopes`** — это `"plugin"`, `"session"` или `"persistent"`.

## Как написать reason

`reason` отрисовывается под собственной меткой Astra для разрешения,
визуально подчинённо, в кавычках, простым текстом, с ограничением в 140
символов, и всегда с префиксом *«The author says:»*. Метка принадлежит
Astra, на языке пользователя; reason — ваш. Вы не можете сформировать саму
метку, и это намеренно: формулировки фиксируются в поставке Astra и не
должны быть записываемыми через листинг.

Хороший reason:

- **называет фичу, которую узнаёт пользователь**, а не API — *«Запускает
  триггер on_dice_roll, который вы настроили»*, а не *«вызывает
  FireTrigger»*;
- **говорит когда**, если не всегда — *«только пока идёт запись»*;
- **не повторяет метку.** Astra уже её отрисовала;
- **не давит.** Никакой срочности, угроз, инструкций пользователю. Лист
  согласия — последнее место для исключения, и текст с bidi-переопределениями
  или соединителями нулевой ширины отклоняется там, где отображается
  дословно.

| Вместо | Пишите |
|---|---|
| `"needs fire_trigger"` | `"Fires the trigger you configure when a roll completes"` |
| `"required for the plugin to work"` | `"Reads command-completion events so it can log the run"` |
| `"full access to the UI"` | `"Draws the timer in the panel this plugin adds to the sidebar"` |
| `"REQUIRED! Do not disable!"` | — удалите разрешение или скажите, для чего оно |

Разрешение без правдоподобного reason — это разрешение, которое надо удалить
из манифеста. Автоматически это никто не проверяет; единственный заслон —
человек, читающий вашу заявку, и `astra-plugin check` скажет вам, когда вы
объявили разрешение, которое не нужно вашим возможностям.

## Что происходит, когда разрешения не хватает

Вызов возвращается с `permission_denied`, с сообщением, называющим
разрешение **и** откуда взялся выданный набор. В тесте это можно
инсценировать ровно так:

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

`astra-plugin doctor` отвечает на этот же вопрос про манифест ещё до того,
как вы его хоть раз запустите:

<!-- doctest: output from="astra-plugin doctor ." -->
```
  [ok  ] Why is a host call coming back `permission_denied`?
         [permissions] grants: none. Every declared capability has the host rpc it needs.
```

## Откуда берётся выданный набор

| Путь установки | Выдано |
|---|---|
| Из каталога, верифицирован | то, что запросил манифест, после согласия |
| Файл `.astraplugin`, импортированный вручную | манифест, **с потолком**: `send_chat_message`, `set_theme_contribution`, `dom_access`, `client` отклоняются безусловно |
| Сайдлоаднутый каталог с исходниками, режим разработчика включён | манифест, без потолка |
| `Untrusted` / `TamperDetected` / `Revoked` | ничего |
| Установлен до появления записей доверия | манифест, с потолком как у импортированного файла |

Полная таблица и обоснование:
[`spec/permissions.md` §4](../spec/permissions.md).

## Согласие, со стороны пользователя

Разрешения сгруппированы по риску. Пять высокорисковых получают каждое свой
чекбокс, и кнопка «Установить» остаётся неактивной, пока не отмечен каждый;
`dom_access` получает второй экран. Намеренно **нет ввода-для-подтверждения**:
это паттерн для необратимого уничтожения, а приучение пользователей печатать,
чтобы пройти его, уничтожает сигнал, который несёт чекбокс.

При обновлении: разрешения, не изменившиеся или сузившиеся, применяются
молча; разрешения, **расширившиеся**, ставят обновление в очередь без
установки и оставляют старую версию работающей, пока пользователь не
рассмотрит разницу. Отказ ничего не стоит.

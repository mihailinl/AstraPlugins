# Публікація плагіна

> Переклад. Джерело істини — [docs/en](../en/publishing.md); за розбіжності відповідає англійська версія.

**Одна сторінка, від порожнього каталогу до плагіна, який можуть
встановити користувачі.** Кожна команда тут по порядку, з виводом, який
вона виробляє. Якщо ви читаєте рівно одну сторінку про публікацію,
читайте саме цю; глибші сторінки пов'язані там, де це важливо, і жодна з
них не обов'язкова, щоб дійти до кінця.

---

## Прочитайте цю частину, навіть якщо більше нічого не прочитаєте

Публікація плагіна в Astra означає **одну конкретну річ**: ви тегуєте
реліз у власному репозиторії GitHub, CI GitHub збирає бандл і засвідчує
його, і ви один раз надсилаєте його в панелі — один раз, назавжди.

Це **не** публікація, і кожне з цього вже пробували:

| Не публікація | Чому це не може спрацювати |
|---|---|
| Пуш ваших вихідників у GitHub | Реєстр ніколи не читає ваше дерево вихідників. Він читає файл `.astraplugin`, прикріплений до релізу, а його немає |
| Надсилання комусь `.zip` або бандла, зібраного на вашому ноутбуці | Ці байти не несуть атестації збірки, тож реєстр їх відхилить, яким би хорошим не був плагін |
| Прохання до мейнтейнера зібрати його за вас | Ніхто не збирає ваш плагін, крім власного CI вашого репозиторію. Іншого збирача немає |
| Опис плагіна реєстру будь-де, крім сторінки надсилання в панелі | Реєстр діє за заявкою, зробленою в панелі, з входом в акаунт, для репозиторію, прив'язаного до вашого акаунта. Інших дверей немає. Див. [Відправка](#8--надішліть-заявку-один-раз-назавжди) |

**Чому це має бути саме так, у двох реченнях.** Реєстр закріплює ваш
плагін за SHA-256 того самого файлу, який завантажить користувач, і читає
атестацію збірки GitHub — підпис Sigstore, випущений з власної
OIDC-ідентичності workflow, — що стверджує, що ці точні байти вийшли з
того workflow, на тому коміті, в тому репозиторії. Файл, який ви зібрали
на своєму ноутбуці і комусь віддали, не несе жодного з цього, тож Astra
нема чого перевірити на машині користувача, а реєстру нема чого
закріплювати.

Ніщо з цього не стверджує, що ваш код безпечний. Див.
[Що встановлює довіру](#що-встановлює-довіру) в кінці цієї сторінки.

---

## Перш ніж почати

<!-- doctest: cli -->
```bash
astra-plugin --version
```

Якщо це нічого не друкує, зупиніться тут і спершу пройдіть
**[встановлення CLI](install-cli.md)**. Тепер є готові бінарники —
завантажте архів для Linux або Windows, звірте його з `SHA256SUMS.txt`, і
жодний тулчейн не потрібен. Збірка з вихідників усе ще працює і
залишається шляхом для macOS і ARM Linux. `cargo install astra-plugin-cli`
— взагалі не шлях; та сторінка пояснює, чому.

> **Не судіть про здоров'я вашої збірки за номером версії.** CLI, зібрана
> до коміту `5b8ab22`, пише workflow релізу, який GitHub відхиляє в момент
> пушу вашого першого тега. Це виправлення потрапило до `master` *раніше*,
> ніж бамп до `0.2.1`, тож збірка може нести його і все одно друкувати
> `0.2.0`, і жодного `0.2.1` без нього не буває. Встановлення з `master`
> сьогодні дає виправлення, хай би що казало число. Питання по-справжньому
> вирішує SHA, який друкує `init-ci`, і ця сторінка запускає його в
> [кроці 3](#3--налаштуйте-workflow-релізу).

Також потрібен **публічний** репозиторій GitHub. Атестації публікуються в
публічний журнал прозорості; у приватному репозиторії для них потрібен
GitHub Enterprise, і workflow релізу скаже про це прямо, а не тихо
вироблятиме незасвідчені бандли.

---

## 1 · Створіть заготовку

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller" unrun="creates a directory tree; re-run it in an empty directory of your own" -->
```
Created plugin project 'dice-roller' at dice-roller/
Language: rust
Template: tool
Capabilities: tools

Next steps:
  cd dice-roller
  cargo build --release
  astra-plugin test .
  astra-plugin dev .
```

`--lang python` і `--lang typescript` створюють заготовки на двох інших
SDK; `--template` обирає, з чого ви починаєте (`tool`, `tts`, `stt`,
`stt-streaming`, `ai-provider`, `ui`, `action-trigger`, `client`, `blank`).
Написання самого плагіна — це [початок роботи](2-tutorial/getting-started.md)
і [сторінки SDK](4-sdk/rust.md).

**Заповніть два поля в `plugin.toml`, перш ніж йти далі.** Заготовка
залишає `author` порожнім, а `description` — загальним, і обидва
опиняються на вашій картці в каталозі:

<!-- doctest: illustrative reason="a fragment of the scaffolded plugin.toml showing the two fields to edit; a complete manifest is checked by the toml-manifest block in reference/manifest.md" -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "An Astra plugin"     # ← what a person reads on the card
author = ""                         # ← fill this in
license = "MIT"                     # ← must be on the registry's SPDX allowlist
```

`icon.svg`, який пише заготовка, — це плейсхолдер; заміна його описана в
[Потрапити до каталогу §як виглядатиме ваша заявка](5-publish/get-listed.md#як-виглядатиме-ваша-заявка).

## 2 · Доведіть, що він працює

<!-- doctest: cli -->
```bash
astra-plugin test .
```

Це набір перевірки відповідності, що запускається проти вашого плагіна як
**справжнього процесу**, що спілкується з мок-демоном, — а не проти типу у
вашому тестовому файлі. Обрізано до вердикту:

<!-- doctest: output from="astra-plugin test ." unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  Registered: port 37173, protocol 1, sdk astra-plugin-sdk-rust 0.6.0
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] CallTool                 required  `hello` answered
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 42.1ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 837.6µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] a call without the daemon's token is refused: HealthCheck without `x-plugin-token` answered UNAUTHENTICATED
  [ok  ] Shutdown is honoured within the grace period: the process exited 42.1ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 1 host call(s) reached the daemon: log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 6 hook(s) exercised, 7 check(s) passed.
```

Щоб запустити його всередині працюючої Astra натомість, `astra-plugin dev
.` — це [сайдлоадинг](5-publish/sideload.md), цикл розробки, і це **не**
спосіб передати плагін комусь іншому.

## 3 · Налаштуйте workflow релізу

Ви не пишете YAML. Одна команда це робить:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

<!-- doctest: output from="astra-plugin init-ci" unrun="writes .github/workflows/release.yml into the working directory; re-run it in your own plugin" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned c3f342469d186ef48458992930bf1b7c583c78d4 (plugin-release/v1)
    with   plugin-dir: .
           tag-prefix: v

  Next: commit this file, then release with
    astra-plugin version <semver>
```

Цей SHA коміту — не прикраса. Це те, на що вказує випущений багаторазовий
workflow `plugin-release/v1`, і це один із SHA, що допускаються підписаним
коренем `trust.json` реєстру — збірка, вироблена будь-яким іншим workflow,
відхиляється з `E_WORKFLOW_NOT_ALLOWED`. Перезапускайте `init-ci` в
будь-який момент, щоб зсунути закріплення вперед; вона зберігає
встановлені вами параметри.

**Перевірте надрукований SHA, перш ніж продовжувати.** Він зобов'язаний
бути тим комітом, на який `plugin-release/v1` вказує сьогодні, а сказати,
який це коміт, може лише віддалений репозиторій: `git ls-remote
https://github.com/mihailinl/AstraPlugins.git refs/tags/plugin-release/v1
'refs/tags/plugin-release/v1^{}'` — обидва refspec, і знята (`^{}`) рядок
перемагає, якщо віддалений її надіслав; саме цю пару питає і сам
`init-ci`. Якщо ваше закріплення розходиться, перезапустіть рядок
`cargo install` зі [встановлення CLI](install-cli.md), потім запустіть
`astra-plugin init-ci` знову — вона перепише закріплення і збереже ваші
параметри. Ніщо не лагодиться на місці, тож наявний `release.yml` тримає
застарілий SHA, поки ви його не перезапустите. Решта — історія, і вона
датована: з 2026-08-11 до 2026-08-19 `plugin-release/v1` був анотованим
тегом, CLI старша за коміт `5b8ab22` закріплювала його об'єкт тега
`dc1a044876926e9cf1170f034e2eab533ec07641` там, де GitHub вимагає коміт, і
це саме той баг, що зламав перший реліз реального автора з
`invalid value workflow reference` ще до старту будь-якого завдання;
сьогодні тег легкий, тож цей SHA більше не друкує жодна збірка.

Подробиці, включно зі вмістом згенерованого файлу і чому потрібен кожен з
трьох його дозволів: [реліз через CI](5-publish/release-with-ci.md).

<!-- doctest: cli -->
```bash
astra-plugin check --strict
```

<!-- doctest: output from="astra-plugin check --strict" unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
```
Checking plugin at ....
  NOTE: Missing plugin.author
  NOTE: Pin freshness not checked (pass --resolve-pin, or set ASTRA_PLUGIN_WORKFLOW_SHA)
  REGISTRY WARN: B_UNBOUND predicted once this listing needs a binding: there is no .well-known/astra-plugin-owner at the repository root (working tree). From the registry's cutover every first listing needs one, and every listing after the binding deadline; a release without it is refused B_UNBOUND. Mint a token in the panel and run `astra-plugin init-ci --binding <token>` — https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/5-publish/get-listed.md#bind-your-repository
  NOT CHECKED: B_BINDING_UNUSABLE, B_OWNER_CHANGED, B_REPOSITORY_RECYCLED, E_WORKFLOW_NOT_ALLOWED — only the registry can answer these, from the plugins service, GitHub and trust.json
  sections: [plugin], [entry], [capabilities]
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
```

`--fix` застосовує все, що можна виправити механічно. `--resolve-pin`
питає у GitHub, чи актуальне ще ваше закріплення workflow; за
замовчуванням вона вимкнена, щоб ні `dev`, ні CI не потребували мережі
для запуску перевірки.

## 4 · Опублікуйте, публічно — з файлом володіння

<!-- doctest: cli -->
```bash
git init && git add -A && git commit -m "dice-roller 0.1.0"
git remote add origin https://github.com/you/dice-roller
git push -u origin main
astra-plugin init-ci --binding <token>
git add .well-known && git commit -m "Bind this repository to my Minice account" && git push
astra-plugin check --strict
```

У перших трьох рядках немає нічого особливого — це звичайний репозиторій. Але
зверніть увагу, чим це *не* є: запушити це — не означає опублікувати плагін, і
зупинитися тут — саме те, на чому спіткнулися дві реальні заявки, через які
з'явилася ця сторінка. Опублікованим плагіном його робить тег на наступному
кроці.

**Рядок прив'язки — це доказ володіння, і він не є необов'язковим.** Між пушем
і `init-ci` увійдіть на https://astra.minice.ai/plugins в акаунт Minice, що
публікуватиме, і випустіть токен прив'язки для `you/dice-roller` — панель
шукає репозиторій на GitHub, тому його треба запушити заздалегідь.
`init-ci --binding` записує токен першим рядком
`.well-known/astra-plugin-owner` у корені вашого репозиторію; закомічений у
гілку за замовчуванням, він те, за чим реєстр дізнається, який акаунт говорить
від імені цього репозиторію, — єдине, чого не може сказати засвідчення
збирання. Пропустіть його — і перша заявка отримає відмову `B_UNBOUND`.

Коли на наступному кроці ви поставите тег, `astra-plugin check --tag v0.1.0`
прочитає рядок із коміту тега, як це зробить реєстр. Токен публічний і не
автентифікує жоден реліз, тому ніколи не мерджте рядок прив'язки, який випустили
не ви. Що він фіксує, скільки живе і що з ним робить перейменування — у
[Потрапити до каталогу — Прив'яжіть репозиторій](5-publish/get-listed.md#привяжіть-репозиторій).

## 5 · Тег — це і є реліз

<!-- doctest: cli -->
```bash
astra-plugin version 0.1.0
git commit -am "release 0.1.0"
git tag v0.1.0
git push && git push --tags
```

<!-- doctest: output from="astra-plugin version 0.2.0" unrun="rewrites every manifest in a plugin project; re-run it in your own plugin" -->
```
Setting version to 0.2.0 (plugin.toml was 0.1.0)
  plugin.toml                    [plugin] version           0.1.0 -> 0.2.0
  Cargo.toml                     [package] version          0.1.0 -> 0.2.0
  2 file(s) rewritten

Release it:
  git commit -am "release 0.2.0"
  git tag v0.2.0
  git push && git push --tags

  The tag must be exactly 'v0.2.0': the release workflow asserts it
  against plugin.toml before it builds anything.
```

`astra-plugin version` переписує `plugin.toml` **і** кожен інший маніфест
у проєкті за одну правку — `Cargo.toml`, `package.json`, `pyproject.toml`
— тож вони не можуть розійтися. Вона відхиляє версію, що сортується
нижче за поточну, якщо ви не передасте `--allow-downgrade`, тому що Astra
відмовляється встановлювати пониження версії, і такий реліз був би
невстановлюваним.

**Тег — це весь процес релізу.** Його пуш запускає ваш `release.yml`, який
викликає закріплений багаторазовий workflow, який виконує три завдання —
завдання `plan`, що читає ваш маніфест як дані і ніколи не запускає ваш
код, матрицю `build`, що запускає ваш код і не тримає токена на запис, і
завдання `publish`, що перераховує кожен дайджест самостійно і засвідчує
те, що захешувала. Цей розподіл і є властивістю безпеки, він описаний у
[реліз через CI §3](5-publish/release-with-ci.md#3--що-робить-ci).

Коли все завершиться, ваш реліз GitHub несе:

<!-- doctest: illustrative reason="the asset names a release ends up with; they are produced by GitHub Actions in the author's own repository, so there is no local command that emits this listing" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
dice-roller-0.1.0-windows-x64.astraplugin
dice-roller-0.1.0.sigstore.jsonl
SHA256SUMS.txt
```

Реліз стає видимим лише після прикріплення кожного артефакту. Rust-плагіни
отримують по одному файлу на платформу; TypeScript і Python — єдиний файл
`noarch`.

**Якщо workflow взагалі не запустився**, звичайна причина — розбіжність
`on: push: tags:` і `tag-prefix:` — глоб, вужчий за префікс, ніколи не
спрацює. Решта режимів збою — у [реліз через CI §що йде не так](5-publish/release-with-ci.md#що-йде-не-так).

## 6 · Перевірте реліз самі

Будь-хто може, не довіряючи ні Astra, ні реєстру:

<!-- doctest: cli -->
```bash
gh release download v0.1.0 --repo you/dice-roller --pattern "*.astraplugin"
gh attestation verify dice-roller-0.1.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" unrun="needs that exact bundle, which is a build artefact and is not committed anywhere" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
  schema:          astra.bundle/2
  plugin:          dice-roller v0.1.0
  target:          linux-x64 (os=linux, arch=x86_64)
  protocol:        1
  capabilities:    tools
  entry:           ./bin/dice_roller
  permissions:     sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a
  artifact sha256: 7f77e3f02a83fdcad96e62b9748c3265b6506e9800e432d0270009bdb4c9fbc3
  manifest digest: a2cc2e1bd38538ca5f087fd0f00efd74328b5b5852c6144ead3849c74e86980d
  size:            2730916 bytes (2666.9 KB)
  legacy in-ZIP signature: absent

  4 listed files:
    0644       1063  a9288520e75b02d6  README.md
    0755    8729640  982348bb71764594  bin/dice_roller
    0644       2509  70e9035f388492b0  icon.svg
    0644       1334  acb85afb406f182c  plugin.toml
  1 unlisted entries: MANIFEST.json

  OK — MANIFEST.json is entry 0 and stored, the file list is exhaustive in both
       directions, and every listed digest, size and mode matches the archive.
```

`astra-plugin verify` виходить з **1**, коли бандл неправильний, і з **2**,
коли CLI не змогла відповісти — наприклад, відсутній файл. Формат архіву і
що зобов'язаний відхилити верифікатор — [`spec/bundle-v2.md`](spec/bundle-v2.md).

## 7 · Передпольотна перевірка заявки

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

Вона прогонить кожну перевірку реєстру, яку можна виконати локально, а
потім — та половина, що важлива, — називає ті, що може виконати лише
реєстр, тож ви знаєте, що ще не доведено:

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the attestation's workflow commit is one the registry's trust.json allows (E_WORKFLOW_NOT_ALLOWED)
  · that the release assets are served from your repository's own release namespace
  · the binding verdict: that the token on the binding line at the tagged commit is bound to a Minice account (B_BINDING_UNUSABLE)
  · eligibility: that the account behind the token may publish (B_ACCOUNT_INELIGIBLE)
  · the ids against the identity record: that the repository and its owner are the ones this listing is recorded under (B_OWNER_CHANGED, B_REPOSITORY_RECYCLED)
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan

  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code
  each failure produces. What happens to a release that passes — published now,
  delayed 24 hours, or held for a person — is docs/POLICY.md.
```

З цього списку вердикт прив'язки — та перевірка, яку вирішує ваша власна
робота, і ви її зробили на
[кроці 4](#4--опублікуйте-публічно--з-файлом-володіння). Решта випливає з
того, що ви затегували реліз, який зібрав workflow.

## 8 · Надішліть заявку, один раз, назавжди

**Перш ніж запускати це**, прочитайте рядок прив'язки з вашого тега рівно так,
як його прочитає реєстр. Це єдина перевірка на цій сторінці, яку можна не
пройти, зробивши все інше правильно:

<!-- doctest: cli -->
```bash
astra-plugin check --tag v0.1.0
astra-plugin publish
```

`publish` відкриває в браузері **сторінку надсилання** панелі з уже заповненими
репозиторієм і тегом. Він нічого не завантажує і не зберігає облікових даних —
немає `astra-plugin login`, немає токена в історії оболонки, нічого
інтегрувати з keyring'ом. Сторінка нічого не надсилає, доки цього не зробите
ви, увійшовши в акаунт Minice, до якого прив'язано ваш репозиторій.
`--print-url` друкує посилання замість відкриття браузера:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project in a bound git repository; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — submission for you/dice-roller@v0.1.0, in the panel

  Bound: `astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd` is line 1 of the owner file at HEAD. Submit in the
  panel signed in to the Minice account that minted that token. The page fills itself
  in from this link and submits nothing until you do. The registry reads the tag's
  commit, not HEAD — `astra-plugin check --tag v0.1.0` reads it the same way.

https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0
```

Заявка несе **два факти**: ваш репозиторій-джерело (`you/dice-roller`) і тег
релізу (`v0.1.0`). Усе інше читається із засвідченого бандла, бо все в бандлі
покрито засвідченням і тому вартує суворо більше, ніж будь-що, вписане у форму.

## 9 · Що відбувається далі

Подробиці, включно з кожним кодом: [Потрапити до каталогу §що відбувається після
відправки](5-publish/get-listed.md#3--що-відбувається-після-відправки). Коротко:
панель показує стан заявки, і ті самі моменти приходять до вас сповіщеннями —
на підтверджену адресу пошти вашого акаунта Minice і в панель, а в Telegram —
лише якщо ви його підключили.

| Наслідок | Означає | Хто бере участь |
|---|---|---|
| **Опубліковано** | Закомічено, потім у підписаному каталозі | ніхто |
| **Відкладено** | Усе пройшло; публікується саме в той час, який показує панель | ніхто |
| **Утримано** | Рішення, яке реєстр не вправі приймати автоматично | модератор, у панелі |
| **Відмовлено** | Перевірку не пройдено | ви: виправте, потім Recheck у панелі або новий тег, як каже код |

**Перший лістинг завжди утримується для людини** — одна з рівно трьох подій,
яким вона потрібна, поряд із уперше запитаним високоризиковим дозволом і зміною
репозиторію чи прив'язки. Модератор схвалює або відхиляє його в панелі; поки ви
чекаєте, ви нічого не робите. Жодне схвалення не скорочує затримку, а правила
публікує `docs/POLICY.md` реєстру.

## 10 · Кожен реліз після цього

Нічого. Поставте тег, а решту зробить CI; реєстр сам помічає новий тег
внесеного до каталогу плагіна, і панель показує його стан.

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

Надсилати нічого і пінгувати нікого. Реліз, який не з'явився, є на сторінці
вашого плагіна в панелі, з його станом і причиною.

## Що встановлює довіру

`astra-plugin build` посилається сюди, тож відповідь живе на цьому якорі,
поки це посилання не переміститься.

**Не будь-який ключ, який у вас є.** `astra-plugin keygen` і
`astra-plugin sign` виробляють опціональний другий фактор — корисний
проти захоплення облікового запису GitHub, тому що ключ живе там, де
немає вкраденої сесії GitHub. Astra не верифікує його проти вашого ключа:
демон звіряє пару `SIGNATURE`/`PUBKEY` всередині ZIP із *закріпленим
ключем видавця Astra*, тож бандл, підписаний вашим власним ключем,
недовірений так само, як непідписаний. І команда, і записи формату, які
вона пише, виводяться з обігу.

**На що Astra реально спирається** — це запис реєстру, що контрпідписує
SHA-256 усього файлу, і — перевірювана ботом реєстру при прийомі, а не
демоном — атестація збірки GitHub, що каже, який workflow, на якому
коміті, в якому репозиторії виробив ці байти.

**Наскільки далеко заякорений ланцюг сьогодні.** Кореневі ключі існують з
обох боків: `astra-registry/registry/v1/root.json` несе `"status":
"provisioned"` і два ключі Ed25519, і `PRODUCTION_ROOT_KEYS` демона
вкомпільовує ті самі два. `registry/v1/trust.json` тепер підписаний
`astra-root-2026a` і делегує ключу підпису індексу,
`astra-index-2026a` — перевірено власною командою реєстру `node
tools/sign-trust.mjs --verify registry/v1/trust.json`, яка також друкує
SHA багаторазових workflow, які бот прийме в атестації — їх два відтоді,
як тег переїхав 2026-08-19: коміт, на який вказує `plugin-release/v1`, і
той, на який він вказував раніше. З 2026-09-20 каталог, який отримують
клієнти, підписаний цим ключем; копії, зафіксовані в `main` реєстру,
`registry/v1/index.json` і `revocations.json`, несуть `"signatures": []`
навмисно, і жоден клієнт їх не читає. **Досі відсутня ланка — підписаний
список відкликання на Pages**, тож відкликання поки не застосовується. Ніщо
тут не обіцяє
гарантії, якої ще немає на місці; див.
[модель безпеки](1-orientation/security.md) і
[`spec/registry-index.md` §0.1](spec/registry-index.md).

**Ніщо з цього не каже, що код безпечний.** Плагін — це нативний процес з
вашими повними правами користувача; пісочниці немає. Лістинг — не
перевірка безпеки — ніхто не читає ваш код, і реєстр каже про це у
власній політиці.

---

## Два інших способи, якими плагін потрапляє на машину

Обидва — для розробників, обидва чогось коштують, і **жоден не є
публікацією**:

- [Встановлення локального файлу `.astraplugin`](5-publish/local-install.md)
  — бандл, отриманий не через каталог. Чотири дозволи відхиляються
  безумовно, що б не просив маніфест.
- [Сайдлоад каталогу з вихідним кодом](5-publish/sideload.md) — цикл
  розробки. Потребує режиму розробника, запускає непідписаний код з
  вашими повними правами користувача і ніколи не запускається
  автоматично.

## Див. також

- [Встановлення CLI](install-cli.md) — звідки береться кожна команда на цій сторінці
- [Реліз через CI](5-publish/release-with-ci.md) — весь workflow повністю
- [Потрапити до каталогу](5-publish/get-listed.md) — заявка і те, що слідує за нею
- [Версіонування](versioning.md) — що означають цифри і скільки триває застарівання
- [`spec/bundle-v2.md`](spec/bundle-v2.md) · [`spec/registry-index.md`](spec/registry-index.md)

# Публикация плагина

> Перевод. Источник истины — [docs/en](../en/publishing.md); при расхождении верна английская версия.

**Одна страница, от пустого каталога до плагина, который могут установить
пользователи.** Каждая команда здесь по порядку, с выводом, который она
производит. Если вы читаете ровно одну страницу о публикации, читайте
именно эту; более глубокие страницы связаны там, где это важно, и ни одна
из них не обязательна, чтобы дойти до конца.

---

## Прочтите эту часть, даже если больше ничего не прочтёте

Публикация плагина в Astra означает **одну конкретную вещь**: вы
тегируете релиз в собственном репозитории GitHub, CI GitHub собирает бандл
и удостоверяет его, и вы отправляете реестру одну заявку на листинг — один
раз, навсегда.

Это **не** публикация, и каждое из этого уже пробовали:

| Не публикация | Почему это не может сработать |
|---|---|
| Пуш ваших исходников в GitHub | Реестр никогда не читает ваше дерево исходников. Он читает файл `.astraplugin`, прикреплённый к релизу, а его нет |
| Отправка кому-то `.zip` или бандла, собранного на вашем ноутбуке | Эти байты не несут аттестации сборки, так что реестр их отклонит, каким бы хорошим ни был плагин |
| Открытие issue с просьбой к мейнтейнеру собрать его за вас | Никто не собирает ваш плагин, кроме собственного CI вашего репозитория. Другого сборщика нет |
| Открытие issue в реестре с описанием плагина в обход формы листинга | Метку `listing` ставит только форма, и только эта метка запускает приём. Пустые issue там теперь отключены, а заявка без метки получает ответ с названием метки вместо тишины — но ответ это не листинг. См. [Отправка](#8--отправьте-заявку-один-раз-навсегда) |

**Почему это должно быть именно так, в двух предложениях.** Реестр
закрепляет ваш плагин по SHA-256 того самого файла, который скачает
пользователь, и читает аттестацию сборки GitHub — подпись Sigstore,
выпущенную из собственной OIDC-идентичности workflow, — которая
утверждает, что эти точные байты вышли из того workflow, на том коммите, в
том репозитории. Файл, который вы собрали на своём ноутбуке и кому-то
отдали, не несёт ни того, ни другого, так что Astra нечего проверить на
машине пользователя, а реестру нечего закреплять.

Ничто из этого не утверждает, что ваш код безопасен. См.
[Что устанавливает доверие](#что-устанавливает-доверие) в конце этой
страницы.

---

## Прежде чем начать

<!-- doctest: cli -->
```bash
astra-plugin --version
```

Если это ничего не печатает, остановитесь здесь и сначала пройдите
**[установку CLI](install-cli.md)**. Это одна строка `cargo install`,
нужен тулчейн Rust, и готовых бинарников пока нет — та страница говорит об
этом прямо и объясняет, что установить.

> **Не судите о здоровье вашей сборки по номеру версии.** CLI, собранная
> до коммита `5b8ab22`, пишет workflow релиза, который GitHub отклоняет в
> момент пуша вашего первого тега. Это исправление попало в `master`
> *раньше*, чем бамп до `0.2.1`, так что сборка может нести его и всё равно
> печатать `0.2.0`, и ни один `0.2.1` без него не бывает. Установка из
> `master` сегодня даёт исправление, что бы ни говорило число. Вопрос
> по-настоящему решает SHA, который печатает `init-ci`, и эта страница
> запускает его в [шаге 3](#3--настройте-workflow-релиза).

Также нужен **публичный** репозиторий GitHub. Аттестации публикуются в
публичный журнал прозрачности; в приватном репозитории для них нужен
GitHub Enterprise, и workflow релиза скажет об этом прямо, а не будет тихо
производить неудостоверенные бандлы.

---

## 1 · Создайте заготовку

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

`--lang python` и `--lang typescript` создают заготовки на двух других
SDK; `--template` выбирает, с чего вы начинаете (`tool`, `tts`, `stt`,
`stt-streaming`, `ai-provider`, `ui`, `action-trigger`, `client`, `blank`).
Написание самого плагина — это [быстрый старт](2-tutorial/getting-started.md)
и [страницы SDK](4-sdk/rust.md).

**Заполните два поля в `plugin.toml`, прежде чем идти дальше.** Заготовка
оставляет `author` пустым, а `description` — общим, и оба оказываются на
вашей карточке в каталоге:

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

`icon.svg`, который пишет заготовка, — это плейсхолдер; замена его описана
в [Попасть в каталог §как будет выглядеть ваша заявка](5-publish/get-listed.md#как-будет-выглядеть-ваша-заявка).

## 2 · Докажите, что он работает

<!-- doctest: cli -->
```bash
astra-plugin test .
```

Это набор проверки соответствия, запускаемый против вашего плагина как
**настоящего процесса**, общающегося с мок-демоном, — а не против типа в
вашем тестовом файле. Обрезано до вердикта:

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

Чтобы запустить его внутри работающей Astra вместо этого, `astra-plugin
dev .` — это [сайдлоадинг](5-publish/sideload.md), цикл разработки, и это
**не** способ передать плагин кому-то другому.

## 3 · Настройте workflow релиза

Вы не пишете YAML. Одна команда делает это:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

<!-- doctest: output from="astra-plugin init-ci" unrun="writes .github/workflows/release.yml into the working directory; re-run it in your own plugin" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned e3329df252a46d747676cb540ae4b986af68a3ad (plugin-release/v1)
    with   plugin-dir: .
           tag-prefix: v

  Next: commit this file, then release with
    astra-plugin version <semver>
```

Этот SHA коммита — не украшение. Это то, на что указывает выпущенный
переиспользуемый workflow `plugin-release/v1`, и это один из SHA,
допускаемых подписанным корнём `trust.json` реестра — сборка, произведённая
любым другим workflow, отклоняется с `E_WORKFLOW_NOT_ALLOWED`.
Перезапускайте `init-ci` в любой момент, чтобы сдвинуть закрепление
вперёд; она сохраняет установленные вами параметры.

**Проверьте напечатанный SHA, прежде чем продолжать.** Он обязан быть
`e3329df252a46d747676cb540ae4b986af68a3ad`. Если это
`dc1a044876926e9cf1170f034e2eab533ec07641`, ваша CLI старше коммита
`5b8ab22`: это SHA *объекта тега* `plugin-release/v1`, а `uses: …@<sha>`
требует коммит, так что ваш первый `git push --tags` провалится с
`invalid value workflow reference` ещё до старта любой задачи. Это та самая
проверка, которую стоит сделать; номер версии на этот вопрос не отвечает,
потому что исправление добралось до `master` раньше, чем изменилось число.
Перезапустите строку `cargo install` из [установки
CLI](install-cli.md), затем запустите `astra-plugin init-ci` снова — она
перепишет закрепление и сохранит ваши параметры. Ничто не чинится на
месте, так что существующий `release.yml` держит плохой SHA, пока вы его
не перезапустите. Это именно тот баг, что сломал первый релиз реального
автора.

Подробности, включая содержимое сгенерированного файла и почему нужно
каждое из трёх его разрешений: [релиз через CI](5-publish/release-with-ci.md).

<!-- doctest: cli -->
```bash
astra-plugin check --strict
```

<!-- doctest: output from="astra-plugin check --strict" unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
```
Checking plugin at ....
  NOTE: Missing plugin.author
  NOTE: Pin freshness not checked (pass --resolve-pin, or set ASTRA_PLUGIN_WORKFLOW_SHA)
  sections: [plugin], [entry], [capabilities]
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
```

`--fix` применяет всё, что можно исправить механически. `--resolve-pin`
спрашивает у GitHub, актуально ли ещё ваше закрепление workflow; по
умолчанию она выключена, чтобы ни `dev`, ни CI не требовали сети для
запуска проверки.

## 4 · Опубликуйте, публично

<!-- doctest: cli -->
```bash
git init && git add -A && git commit -m "dice-roller 0.1.0"
git remote add origin https://github.com/you/dice-roller
git push -u origin main
astra-plugin check --strict
```

В этом шаге нет ничего особенного — это обычный репозиторий. Но обратите
внимание, чем он *не является*: пуш этого — не публикация плагина, и
остановка здесь — это как раз то место, где ошиблись две реальные заявки,
подтолкнувшие к созданию этой страницы. Что делает его опубликованным
плагином — это тег на следующем шаге.

## 5 · Тег — это и есть релиз

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

`astra-plugin version` переписывает `plugin.toml` **и** каждый другой
манифест в проекте за одну правку — `Cargo.toml`, `package.json`,
`pyproject.toml` — так что они не могут разойтись. Она отклоняет версию,
которая сортируется ниже текущей, если вы не передадите
`--allow-downgrade`, потому что Astra отказывается устанавливать понижение
версии, и такой релиз был бы неустанавливаемым.

**Тег — это весь процесс релиза.** Его пуш запускает ваш `release.yml`,
который вызывает закреплённый переиспользуемый workflow, который
выполняет три задачи — задачу `plan`, читающую ваш манифест как данные и
никогда не запускающую ваш код, матрицу `build`, запускающую ваш код и не
держащую токена на запись, и задачу `publish`, пересчитывающую каждый
дайджест самостоятельно и удостоверяющую то, что захешировала. Это
разделение и есть свойство безопасности, оно описано в
[релиз через CI §3](5-publish/release-with-ci.md#3--что-делает-ci).

Когда всё завершится, ваш релиз GitHub несёт:

<!-- doctest: illustrative reason="the asset names a release ends up with; they are produced by GitHub Actions in the author's own repository, so there is no local command that emits this listing" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
dice-roller-0.1.0-windows-x64.astraplugin
dice-roller-0.1.0.sigstore.jsonl
SHA256SUMS.txt
```

Релиз становится видимым только после прикрепления каждого артефакта.
Rust-плагины получают по одному файлу на платформу; TypeScript и Python —
единый файл `noarch`.

**Если workflow вообще не запустился**, обычная причина — расхождение `on:
push: tags:` и `tag-prefix:` — глоб, более узкий, чем префикс, никогда не
сработает. Остальные режимы сбоя — в
[релиз через CI §что идёт не так](5-publish/release-with-ci.md#что-идёт-не-так).

## 6 · Проверьте релиз сами

Любой может, не доверяя ни Astra, ни реестру:

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

`astra-plugin verify` выходит с **1**, когда бандл неправильный, и с
**2**, когда CLI не смогла ответить — например, отсутствующий файл. Формат
архива и что обязан отклонить верификатор — [`spec/bundle-v2.md`](spec/bundle-v2.md).

## 7 · Предполётная проверка заявки

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

Она прогоняет каждую проверку реестра, которую можно выполнить локально, а
затем — та половина, что важна, — называет те, что может выполнить только
реестр, так что вы знаете, что ещё не доказано:

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the release assets are served from your repository's own release namespace
  · that you have admin or maintain on the repository
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan

  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code
  each failure produces. What happens to a release that passes — published now,
  delayed 24 hours, or held for a person — is docs/POLICY.md.
```

## 8 · Отправьте заявку, один раз навсегда

<!-- doctest: cli -->
```bash
astra-plugin publish
```

Она открывает **предзаполненный issue в реестре** в вашем браузере. Она
ничего не загружает и не хранит никаких учётных данных — нет `astra-plugin
login`, нет токена в истории вашей оболочки, нечего интегрировать с
keyring'ом. `--print-url` печатает ссылку вместо открытия браузера:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — listing request for you/dice-roller@v0.1.0

  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI
  build and attest, and the registry picks it up. Everything on the store card —
  name, summary, licence, capabilities, permissions, digests — is read out of the
  attested bundle, so there is nothing else to fill in and nothing to keep in sync.

https://github.com/mihailinl/astra-registry/issues/new?template=plugin-listing.yml&title=%5Blisting%5D+you%2Fdice-roller&repository=you%2Fdice-roller&release_tag=v0.1.0
```

> **Используйте именно эту ссылку.** `template=plugin-listing.yml` в ней —
> несущая часть: шаблон issue объявляет `labels: ["listing",
> "needs-triage"]`, и бот реестра входит в путь обработки заявки только
> для issue с меткой `listing`. Больше её не ставит никто — в том числе,
> намеренно, и сам бот: в том репозитории эта метка не категория, а токен
> полномочий.
>
> Раньше это молча ломалось. Две заявки от реального автора пришли без
> меток, триаж вернул `mode: "none"`, шаги проверки, публикации и
> комментирования были пропущены, и **им вообще никто не ответил, даже
> отказом** — именно поэтому существует эта страница. Сейчас закрыты обе
> половины: реестр отключил пустые issue, так что форма — единственная
> дверь, а заявка, которая всё же приходит без метки, получает комментарий
> с названием метки и одним кликом, который запускает проверку на том же
> issue. Ссылкой всё равно пользуйтесь: это путь, на котором приём
> начинается без чьего-либо вмешательства.

Заявка несёт **два факта**: ваш исходный репозиторий (`you/dice-roller`) и
тег релиза (`v0.1.0`), плюс два подтверждения — что вы владеете
репозиторием или являетесь его мейнтейнером, и что вы прочли политику.
Всё остальное считывается из удостоверенного бандла, потому что всё в
бандле покрыто аттестацией и поэтому строго надёжнее, чем что-либо,
введённое в форму.

## 9 · Что происходит дальше

Подробности, включая каждый код причины: [Попасть в каталог §что
происходит после отправки](5-publish/get-listed.md#3-что-происходит-после-отправки).
Короткая версия:

| Исход | Значит | Кто вовлечён |
|---|---|---|
| **Опубликовано** | Зафиксировано и попадёт в каталог при следующей сборке индекса | никто |
| **Отложено** | Всё прошло; публикуется само в указанное время | никто |
| **Удержано** | Решение, которое реестр не вправе принимать автоматически | мейнтейнер, в течение **48 ч** |
| **Отклонено** | Провалилась проверка | вы: исправьте и прокомментируйте `/recheck` в issue |

**Первая заявка на листинг всегда удерживается для человека** — это одно
из ровно трёх событий, которым он нужен, наряду с впервые запрошенным
высокорисковым разрешением и сменой репозитория. 48 часов — опубликованный
SLA для всех них.

Удержание снимается мейнтейнером, комментирующим `/approve` в вашем issue,
что заново прогоняет каждую проверку с нуля, а не доверяет чему-либо
закешированному. Вы не вводите эту команду, и вам не нужно ничего делать,
пока вы ждёте. См. [как снимается удержание](5-publish/get-listed.md#как-снимается-удержание).

Бот комментирует ваш issue с итогом и причиной в любом случае — и теперь
комментирует даже тогда, когда работу *не* начинает, то есть в том самом сбое
из шага 8. Если за час никто не прокомментировал, проверьте метку `listing`.
Если её нет, попросите мейнтейнера её поставить: простановка метки порождает то
же событие, что и новая заявка, так что проверка запустится на этом же issue и
ничего не придётся набирать заново.

## 10 · Каждый релиз после этого

Ничего. Тег, и CI делает остальное; реестр замечает релиз и перегенерирует
индекс.

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

Если реестр не заметил в течение нескольких минут:

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

Это ручной пинг для плагина, который **уже в каталоге**. Без `--notify`
`publish` вместо этого открывает заявку на первый листинг, а это не то,
что вам нужно на втором релизе.

---

## Что устанавливает доверие

`astra-plugin build` ссылается сюда, так что ответ живёт на этом якоре,
пока эта ссылка не переместится.

**Не любой ключ, который у вас есть.** `astra-plugin keygen` и
`astra-plugin sign` производят опциональный второй фактор — полезный
против захвата аккаунта GitHub, потому что ключ живёт там, где нет
украденной сессии GitHub. Astra не верифицирует его против вашего ключа:
демон сверяет пару `SIGNATURE`/`PUBKEY` внутри ZIP с *закреплённым
публикующим ключом Astra*, так что бандл, подписанный вашим собственным
ключом, недоверенный ровно так же, как неподписанный. И команда, и записи
формата, которые она пишет, выводятся из обращения.

**На что Astra реально опирается** — это запись реестра, контрподписывающая
SHA-256 всего файла, и — проверяемая ботом реестра при приёме, а не
демоном — аттестация сборки GitHub, говорящая, какой workflow, на каком
коммите, в каком репозитории произвёл эти байты.

**Насколько далеко заякорена цепочка сегодня.** Корневые ключи существуют
с обеих сторон: `astra-registry/registry/v1/root.json` несёт `"status":
"provisioned"` и два ключа Ed25519, и `PRODUCTION_ROOT_KEYS` демона
вкомпилирует те же два. `registry/v1/trust.json` теперь подписан
`astra-root-2026a` и делегирует ключу подписи индекса,
`astra-index-2026a` — проверено собственной командой реестра `node
tools/sign-trust.mjs --verify registry/v1/trust.json`, которая также
печатает единственный SHA переиспользуемого workflow, который бот примет в
аттестации (`e3329df252a46d747676cb540ae4b986af68a3ad`, коммит, на
который указывает `plugin-release/v1`). **Всё ещё недостающее звено — это
подпись самого каталога:** `registry/v1/index.json` и `revocations.json`
несут `"signatures": []`, так что обычной сборке Astra нечего проверять, и
она классифицирует любой каталог как неподписанный. Ничто здесь не
обещает гарантии, которой ещё нет на месте; см.
[модель безопасности](1-orientation/security.md) и
[`spec/registry-index.md` §0.1](spec/registry-index.md).

**Ничто из этого не говорит, что код безопасен.** Плагин — это нативный
процесс с вашими полными правами пользователя; песочницы нет. Листинг —
не проверка безопасности — никто не читает ваш код, и реестр говорит об
этом в собственной политике.

---

## Два других способа, которыми плагин попадает на машину

Оба — для разработчиков, оба чего-то стоят, и **ни один не является
публикацией**:

- [Установка локального файла `.astraplugin`](5-publish/local-install.md)
  — бандл, полученный не через каталог. Четыре разрешения отклоняются
  безусловно, что бы ни просил манифест.
- [Сайдлоад каталога с исходниками](5-publish/sideload.md) — цикл
  разработки. Требует режима разработчика, запускает неподписанный код с
  вашими полными правами пользователя и никогда не запускается
  автоматически.

## См. также

- [Установка CLI](install-cli.md) — откуда берётся каждая команда на этой странице
- [Релиз через CI](5-publish/release-with-ci.md) — весь workflow целиком
- [Попасть в каталог](5-publish/get-listed.md) — заявка и то, что следует за ней
- [Версионирование](versioning.md) — что значат цифры и сколько длится устаревание
- [`spec/bundle-v2.md`](spec/bundle-v2.md) · [`spec/registry-index.md`](spec/registry-index.md)

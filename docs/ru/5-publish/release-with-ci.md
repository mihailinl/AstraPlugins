# Релиз через CI

> Перевод. Источник истины — [docs/en](../../en/5-publish/release-with-ci.md); при расхождении верна английская версия.

**Тег — это весь процесс релиза.** Одна команда его настраивает, и после
этого вы больше никогда не собираете бандл вручную.

Всё на этой странице начинается с бинарника `astra-plugin`. Если у вас его
нет, сначала [установите CLI](../install-cli.md) — скачайте готовый архив
либо соберите из исходников, если хотите. Весь путь на
одной странице, а не только эта ступень: [Публикация плагина](../publishing.md).

## Почему не просто `astra-plugin build` и загрузить это?

Потому что ничто не поручится за файл, который вы собрали на своём
ноутбуке. Реестр читает **аттестацию сборки** GitHub — подпись Sigstore без
ключа, выпущенную из OIDC-идентичности workflow, — которая говорит *эти
точные байты пришли из того workflow, на том коммите, в том репозитории*.
Ручной бандл не несёт ничего подобного и отклоняется, каким бы хорошим он ни
был, — с именем ошибки `E_ATTESTATION_MISSING`.

По той же причине **пуш вашего исходного кода в GitHub — это не релиз**, и
отправка кому-то собранного локально `.astraplugin` — тоже. Реестр никогда
не читает ваше дерево исходников; он читает артефакты тегированного релиза и
закрепляет их по дайджесту.

Вам не нужен ключ подписи, и его у вас не спрашивают. См.
[модель безопасности](../1-orientation/security.md).

## 1 · Напишите workflow

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

**Это работает сегодня, и обе половины этого можно проверить.**
`.github/workflows/plugin-release.yml` лежит на дефолтной ветке
`mihailinl/AstraPlugins` — `git ls-tree -r master --name-only
.github/workflows` его перечисляет, — и выпущенный тег существует: `git
ls-remote --tags origin` разрешает `plugin-release/v1` в
`e3329df252a46d747676cb540ae4b986af68a3ad`. Поскольку тег существует,
`init-ci` закрепляет этот коммит, а не движущуюся голову ветки, и больше не
печатает оговорку «Not verified», которую цитировали более ранние версии
этой страницы.

Этот SHA — тот же самый, что подписанный корнём `trust.json` реестра
допускает в аттестации сборки — `node tools/sign-trust.mjs --verify
registry/v1/trust.json` в `astra-registry` печатает его под *SHA
переиспользуемых workflow, которые допускаются*. Сборка, произведённая
любым другим workflow, отклоняется при приёме с `E_WORKFLOW_NOT_ALLOWED`,
так что закрепление — не любезность; именно оно делает вашу аттестацию тем,
на основании чего реестр может действовать.

Перезапускайте `init-ci`, когда выходит новый `plugin-release/vN`; она
сохраняет ваши входные параметры и только сдвигает закрепление.

Это весь CI на стороне автора. Он короткий, потому что делегирует:

<!-- doctest: illustrative reason="the file `astra-plugin init-ci` writes; it lives in the author's repository, not in this one, and its pin is resolved at generation time" -->
```yaml
name: Release

on:
  push:
    tags: ["v*"]

# Required, and required HERE: a reusable workflow can only reduce the
# permissions its caller granted, never grant itself more. Leave all three.
permissions:
  contents: write       # create the Release and upload assets
  id-token: write       # mint the OIDC token that makes signing keyless
  attestations: write   # store the build attestation on GitHub

jobs:
  release:
    # Pinned by commit SHA, not by a moving tag: whoever can move
    # `plugin-release/v1` in mihailinl/AstraPlugins would otherwise own the build
    # step of every plugin that trusts it — and that build step runs in YOUR
    # repository with the token above. `astra-plugin init-ci` keeps this current.
    uses: mihailinl/AstraPlugins/.github/workflows/plugin-release.yml@e3329df252a46d747676cb540ae4b986af68a3ad  # plugin-release/v1
    with:
      plugin-dir: .
      tag-prefix: "v"
      linux-packages: ""      # e.g. "libasound2-dev pkg-config" for audio plugins
    # No `secrets: inherit`, deliberately. This workflow declares no secrets,
    # so the job that runs your build.rs and your npm lifecycle scripts has
    # nothing to leak.
```

Перезапустите `init-ci`, чтобы сдвинуть закрепление вперёд; она сохраняет
установленные вами параметры. `--offline` оставляет закрепление, уже
записанное в файле, а `--ref <sha-или-ref>` закрепляет что-то конкретное.

## 2 · Тег

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

`astra-plugin version` переписывает `plugin.toml` **и** каждый другой
манифест в проекте за одну правку — `Cargo.toml`, `package.json`,
`pyproject.toml` — так что они не могут разойтись. Она отклоняет версию,
которая сортируется ниже текущей, если вы не передадите
`--allow-downgrade`, потому что Astra отказывается устанавливать понижение
версии, и такой релиз был бы неустанавливаемым.

Тег обязан совпадать с `tag-prefix` плюс версия манифеста, и CI это
проверяет прежде, чем что-либо собирать. `astra-plugin version` печатает
точный тег, который нужно использовать:

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

## 3 · Что делает CI

Этот раздел описывает `.github/workflows/plugin-release.yml`, как он
написан в этом репозитории, на `master`, на коммите, на который указывает
`plugin-release/v1` — том самом, который вызывает ваш `release.yml`.

Три задачи, и это разделение и есть свойство безопасности.

| Задача | Запускает ваш код | Держит токен на запись | Что делает |
|---|---|---|---|
| **plan** | **нет** | да | Читает `plugin.toml` через `tomllib` Python как *данные*, проверяет тег == версия, решает матрицу сборки, создаёт черновой релиз |
| **build** (матрица) | да | **нет** | `astra-plugin check --strict`, `astra-plugin build`, верификация, распаковка, проверка нижней границы glibc и самодостаточности бандла TypeScript |
| **publish** | нет | да | Пересчитывает каждый дайджест сама, пишет `SHA256SUMS.txt`, удостоверяет, загружает, снимает черновик с релиза |

`plan` никогда не выполняет ничего из репозитория — никаких сабмодулей,
никаких учётных данных, сохранённых в `.git/config`. `build` запускает ваш
`build.rs` и ваши lifecycle-скрипты и не имеет токена, который можно
украсть. `publish` скачивает артефакты, хеширует их сама и удостоверяет то,
что захешировала.

Матрица решается по языку вашего плагина: `linux-x64` + `windows-x64` для
Rust, единственная ветка `noarch` для TypeScript и Python.

### Что попадает в релиз

| Артефакт | |
|---|---|
| `<id>-<version>-linux-x64.astraplugin` | по одному на ключ платформы |
| `<id>-<version>-windows-x64.astraplugin` | |
| `<id>-<version>.sigstore.jsonl` | пакет аттестации, так что пользователь без сети до GitHub всё равно может проверить |
| `SHA256SUMS.txt` | те же дайджесты, что записывает реестр |

Релиз становится видимым только после прикрепления каждого артефакта.

### Аттестация требует публичного репозитория

Аттестации сборки публикуются в публичный журнал прозрачности; в приватном
репозитории для них нужен GitHub Enterprise. Workflow определяет видимость
вашего репозитория и, когда она не публичная, говорит об этом в сводке
задачи и производит **неудостоверенные** бандлы — которые реестр не
включит в каталог. Это реальное ограничение, и оно падает громко, а не
производит релиз, который выглядит нормально.

### Воспроизводимость

`astra-plugin build --reproducible` проверяет детерминированную упаковку:
отсортированные записи, фиксированный mtime, фиксированный уровень сжатия.
Две сборки из одних и тех же входных данных производят один sha256. CI
запускает канарейку воспроизводимости на каждом релизе, что и делает
пересборку третьей стороной осмысленной.

## 4 · Проверьте сами

Любой может верифицировать релиз, не доверяя ни Astra, ни реестру:

<!-- doctest: cli -->
```bash
gh attestation verify dice-roller-0.2.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.2.0-linux-x64.astraplugin
```

`astra-plugin verify` сама читает бандл и печатает, что нашла:

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

Здесь важны коды выхода, и каждый workflow релиза ветвится по ним: **1**
значит, что бандл неправильный, **2** значит, что CLI не смогла ответить —
например, отсутствующий файл. Формат архива и что обязан отклонить
верификатор — [`spec/bundle-v2.md`](../spec/bundle-v2.md).

## 5 · Затем попадите в каталог

Один раз. → [Попасть в каталог](get-listed.md).

## Что идёт не так

| Симптом | Причина |
|---|---|
| Workflow вообще не запускается | `on: push: tags:` и `tag-prefix:` расходятся. Глоб, более узкий, чем префикс, никогда не сработает |
| «tag does not match the manifest version» | Выполните `astra-plugin version <v>` и закоммитьте перед тегированием |
| Сборка под Linux падает на отсутствующем заголовке | Установите `linux-packages: "libasound2-dev pkg-config"` в вызывающем workflow |
| Бандл не удостоверен | Репозиторий приватный |
| `MODULE_NOT_FOUND` при первом запуске | Зависимость TypeScript, которую бандлер не смог отследить. CI это проверяет; посмотрите externals бандлера |
| Ошибка glibc на машине пользователя | Что-то в архиве требует символ выше `GLIBC_2.39`. CI это тоже проверяет |
| `invalid value workflow reference` до старта любой задачи | Закрепление называет коммит, который не несёт `plugin-release.yml`. Перезапустите `astra-plugin init-ci`, чтобы перезакрепиться на `plugin-release/v1` |
| Реестр отклоняет релиз с `E_WORKFLOW_NOT_ALLOWED` | Сборка не запустила закреплённый переиспользуемый workflow Astra. Перезапустите `init-ci`, перетегируйте и дайте CI пересобрать |

Подробнее: [диагностика](../6-operate/troubleshooting.md).

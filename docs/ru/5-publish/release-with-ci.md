# Релиз через CI

**Тег — это весь процесс релиза.** Одна команда всё настраивает, и после неё вы
больше никогда не собираете бандл руками.

## Почему не просто `astra-plugin build` и загрузка файла

Потому что за файл, собранный на вашем ноутбуке, никто не ручается. Реестр
читает **аттестацию сборки** GitHub — keyless-подпись Sigstore, выпущенную по
OIDC-личности workflow, — которая говорит: *эти байты пришли из такого-то
workflow, на таком-то коммите, в таком-то репозитории*. У бандла, собранного
руками, такого нет, и он будет отклонён, каким бы хорошим ни был.

Ключ подписи вам не нужен, и его не спрашивают. См.
[модель безопасности](../1-orientation/security.md).

## 1 · Написать workflow

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

<!-- doctest: output from="astra-plugin init-ci ." -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned 985ad7ebab49957cc4e000edd814a62605579ff0 (default branch)
    with   plugin-dir: .
           tag-prefix: v

  Note: 'plugin-release/v1' does not exist in mihailinl/AstraPlugins yet, so this pins the
  current head of its default branch. Re-run `astra-plugin init-ci` once the
  tag exists to move onto a released workflow.

  Not verified: whether .github/workflows/plugin-release.yml exists at that commit. If
  the tag push fails with 'invalid value workflow reference', it does not;
  pin one that does with `astra-plugin init-ci --ref <commit>`.

  Next: commit this file, then release with
    astra-plugin version <semver>
```

> **Релиз через CI пока не работает, и эта страница обязана об этом сказать.**
> Файла `plugin-release.yml` нет в ветке по умолчанию репозитория
> `mihailinl/AstraPlugins`. Он существует только в ветке, которая несёт эту
> документацию, а она не запушена — `git ls-remote origin` показывает `master`
> и одну feature-ветку, и ни в одном из этих деревьев файла нет. Значит коммит,
> который вычисляет `init-ci`, — настоящий неизменяемый коммит, **в котором нет
> того workflow, на который он ссылается**, и пуш тега сегодня падает в GitHub
> Actions ещё до старта любой job:
>
> ```
> invalid value workflow reference: no version found for owner mihailinl
> repo AstraPlugins workflow .github/workflows/plugin-release.yml
> ```
>
> Ничего не собирается, ничего не аттестуется, ассеты релиза не появляются — а
> значит и до [листинга](get-listed.md) дойти нельзя: его предусловие — релиз,
> собранный CI.
>
> Всё это станет правдой в тот момент, когда эта работа попадёт в ветку по
> умолчанию или будет помечена тегом `plugin-release/v1`; тогда перезапустите
> `init-ci`, и он перепинит на коммит, в котором файл есть. До тех пор
> единственный работающий пин — тот, который вы назовёте сами, указав коммит,
> где вы этот файл проверили:
>
> ```bash
> astra-plugin init-ci --ref <40-hex коммит, содержащий plugin-release.yml>
> ```
>
> `init-ci` пишет про это «Not verified» — и лучше не может: он резолвит ref
> через `git ls-remote`, который отвечает коммитами и ничего не знает о файлах
> внутри них (`astra-plugin-cli/src/commands/init_ci.rs`).

Заметка в выводе выше — про *происхождение* пина, и она верна всегда, когда вы
её читаете: пока тега `plugin-release/v1` нет, `init-ci` закрепляет head ветки
по умолчанию. Тег добавил бы обещание, что то, на что он указывает, не меняет
форму. Перезапустите `init-ci`, когда тег появится: он сохраняет ваши входные
параметры и двигает только пин.

Это весь CI на стороне автора. Он короткий, потому что делегирует:

<!-- doctest: illustrative reason="файл, который пишет astra-plugin init-ci; он живёт в репозитории автора, а не в этом, и пин вычисляется при генерации" -->
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
    # Pinned by commit SHA, not by a moving tag: whoever can move a tag in
    # mihailinl/AstraPlugins would otherwise own the build step of every plugin
    # that trusts it — and that build step runs in YOUR repository with the
    # token above. `astra-plugin init-ci` keeps this line current.
    uses: mihailinl/AstraPlugins/.github/workflows/plugin-release.yml@985ad7eb…
    with:
      plugin-dir: .
      tag-prefix: "v"
      linux-packages: ""      # e.g. "libasound2-dev pkg-config" for audio plugins
    # No `secrets: inherit`, deliberately. This workflow declares no secrets,
    # so the job that runs your build.rs and your npm lifecycle scripts has
    # nothing to leak.
```

Повторный `init-ci` двигает пин вперёд и сохраняет заданные вами входы.
`--offline` оставляет пин, который уже в файле, а `--ref <sha-или-ref>`
закрепляет конкретную ревизию.

## 2 · Поставить тег

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

`astra-plugin version` правит `plugin.toml` **и** все остальные манифесты
проекта одной операцией — `Cargo.toml`, `package.json`, `pyproject.toml`, —
поэтому они не могут разойтись. Он отказывается ставить версию ниже текущей без
`--allow-downgrade`, потому что Astra отказывается устанавливать понижение и
такой релиз был бы неустанавливаемым.

Тег обязан совпадать с `tag-prefix` плюс версия из манифеста, и CI это
проверяет.

## 3 · Что делает CI

Три задачи, и это разделение и есть свойство безопасности.

| Задача | Запускает ваш код | Держит токен на запись | Что делает |
|---|---|---|---|
| **plan** | **нет** | да | Читает `plugin.toml` через `tomllib` Python как *данные*, сверяет тег с версией, решает матрицу сборки, создаёт черновой Release |
| **build** (матрица) | да | **нет** | `astra-plugin check --strict`, `astra-plugin build`, verify, распаковка, проверка порога glibc и самодостаточности TypeScript-бандла |
| **publish** | нет | да | Сам пересчитывает все дайджесты, пишет `SHA256SUMS.txt`, выдаёт аттестацию, загружает, снимает черновик |

`plan` не выполняет ничего из репозитория — ни сабмодулей, ни сохранённых в
`.git/config` учётных данных. `build` выполняет ваш `build.rs` и lifecycle-скрипты
и не имеет токена, который можно украсть. `publish` скачивает артефакты, сам их
хеширует и выдаёт аттестацию на то, что захешировал.

Матрица определяется языком плагина: `linux-x64` + `windows-x64` для Rust, одна
задача `noarch` для TypeScript и Python.

### Что появляется в Release

| Файл | |
|---|---|
| `<id>-<version>-linux-x64.astraplugin` | по одному на ключ платформы |
| `<id>-<version>-windows-x64.astraplugin` | |
| `<id>-<version>.sigstore.jsonl` | бандл аттестации, чтобы проверить можно было и без доступа к GitHub |
| `SHA256SUMS.txt` | те же дайджесты, которые записывает реестр |

Release становится видимым только после того, как приложены все файлы.

### Аттестация требует публичного репозитория

Аттестации сборки публикуются в общедоступный журнал прозрачности; в приватном
репозитории они требуют GitHub Enterprise. Workflow определяет видимость
репозитория и, если он не публичный, пишет это в сводке задачи и выпускает
**неаттестованные** бандлы, которые реестр не примет. Это реальное ограничение,
и оно падает громко, а не выпускает релиз, который выглядит нормально.

### Воспроизводимость

`astra-plugin build --reproducible` требует детерминированной упаковки:
отсортированные записи, фиксированный mtime, фиксированный уровень сжатия. Две
сборки из одних входов дают одинаковый sha256. CI прогоняет канарейку
воспроизводимости на каждом релизе — именно это делает чужую пересборку
осмысленной.

## 4 · Проверить самому

Проверить релиз может кто угодно, не доверяя ни Astra, ни реестру:

<!-- doctest: cli -->
```bash
gh attestation verify dice-roller-0.2.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.2.0-linux-x64.astraplugin
```

`astra-plugin verify` читает бандл сам и печатает, что нашёл:

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
  schema:          astra.bundle/2
  plugin:          dice-roller v0.1.0
  target:          linux-x64 (os=linux, arch=x86_64)
  protocol:        1
  capabilities:    tools
  entry:           ./bin/dice_roller
  permissions:     sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a
  artifact sha256: d7dd70c5b2c4341af51a9ec29e63adc25f5a31d6b5d8f189c1d39e4f77780eb4
  manifest digest: 7d66d26977a939f849f998009eb48b12ac7c741b69338be1cc6247a5ed64df6c
  size:            2730385 bytes (2666.4 KB)
  legacy in-ZIP signature: absent

  3 listed files:
    0644        210  206e62245f5205c3  README.md
    0755    8727528  d8b2a8fa76e520bd  bin/dice_roller
    0644       1334  acb85afb406f182c  plugin.toml
  1 unlisted entries: MANIFEST.json

  OK — MANIFEST.json is entry 0 and stored, the file list is exhaustive in both
       directions, and every listed digest, size and mode matches the archive.
```

Коды возврата здесь важны, и каждый релизный workflow на них ветвится: **1** —
бандл неверен, **2** — CLI не смог ответить, например файла нет. Формат архива и
то, что верификатор обязан отвергнуть, —
[`spec/bundle-v2.md`](../../en/spec/bundle-v2.md).

## 5 · Дальше — в каталог

Один раз. → [Попасть в каталог](get-listed.md).

## Что обычно ломается

| Симптом | Причина |
|---|---|
| Workflow не запускается | `on: push: tags:` и `tag-prefix:` не согласованы. Более узкая маска не срабатывает никогда |
| «tag does not match the manifest version» | Выполните `astra-plugin version <v>` и закоммитьте до тега |
| Linux-сборка падает на отсутствующем заголовке | Задайте `linux-packages: "libasound2-dev pkg-config"` в вызывающем workflow |
| Бандл без аттестации | Репозиторий приватный |
| `MODULE_NOT_FOUND` при первом запуске | TypeScript-зависимость, которую бандлер не отследил. CI это проверяет; посмотрите externals бандлера |
| Ошибка glibc на машине пользователя | Что-то в архиве требует символ выше `GLIBC_2.39`. Это CI тоже проверяет |

Ещё: [диагностика](../6-operate/troubleshooting.md).

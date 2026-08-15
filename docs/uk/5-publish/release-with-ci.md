# Реліз через CI

> Переклад. Джерело істини — [docs/en](../../en/5-publish/release-with-ci.md); за розбіжності відповідає англійська версія.

**Тег — це весь процес релізу.** Одна команда його налаштовує, і після цього
ви більше ніколи не збираєте бандл вручну.

Усе на цій сторінці починається з бінарника `astra-plugin`. Якщо у вас його
немає, спершу [встановіть CLI](../install-cli.md) — один рядок `cargo
install`, потрібен тулчейн Rust, готових бінарників поки немає. Весь шлях на
одній сторінці, а не лише цей щабель: [Публікація плагіна](../publishing.md).

## Чому не просто `astra-plugin build` і завантажити це?

Тому що ніщо не поручиться за файл, який ви зібрали на своєму ноутбуці.
Реєстр читає **атестацію збірки** GitHub — підпис Sigstore без ключа,
випущений з OIDC-ідентичності workflow, — що каже *ці точні байти прийшли з
того workflow, на тому коміті, в тому репозиторії*. Ручний бандл не несе
нічого подібного і відхиляється, яким би хорошим він не був, — з ім'ям
помилки `E_ATTESTATION_MISSING`.

З тієї самої причини **пуш вашого вихідного коду в GitHub — це не реліз**, і
надсилання комусь зібраного локально `.astraplugin` — теж ні. Реєстр ніколи
не читає ваше дерево вихідників; він читає артефакти тегованого релізу і
закріплює їх за дайджестом.

Вам не потрібен ключ підпису, і його у вас не питають. Див.
[модель безпеки](../1-orientation/security.md).

## 1 · Напишіть workflow

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

**Це працює сьогодні, і обидві половини цього можна перевірити.**
`.github/workflows/plugin-release.yml` лежить на дефолтній гілці
`mihailinl/AstraPlugins` — `git ls-tree -r master --name-only
.github/workflows` його перелічує, — і випущений тег існує: `git ls-remote
--tags origin` розв'язує `plugin-release/v1` в
`e3329df252a46d747676cb540ae4b986af68a3ad`. Оскільки тег існує, `init-ci`
закріплює цей коміт, а не рухому голову гілки, і більше не друкує
застереження «Not verified», яке цитували раніші версії цієї сторінки.

Цей SHA — той самий, що підписаний коренем `trust.json` реєстру допускає в
атестації збірки — `node tools/sign-trust.mjs --verify
registry/v1/trust.json` в `astra-registry` друкує його під *SHA
багаторазових workflow, які допускаються*. Збірка, вироблена будь-яким
іншим workflow, відхиляється при прийомі з `E_WORKFLOW_NOT_ALLOWED`, тож
закріплення — не люб'язність; саме воно робить вашу атестацію тим, на
основі чого реєстр може діяти.

Перезапускайте `init-ci`, коли виходить новий `plugin-release/vN`; вона
зберігає ваші вхідні параметри і лише зсуває закріплення.

Це весь CI на боці автора. Він короткий, тому що делегує:

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

Перезапустіть `init-ci`, щоб зсунути закріплення вперед; вона зберігає
встановлені вами параметри. `--offline` залишає закріплення, вже записане у
файлі, а `--ref <sha-або-ref>` закріплює щось конкретне.

## 2 · Тег

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

`astra-plugin version` переписує `plugin.toml` **і** кожен інший маніфест у
проєкті за одну правку — `Cargo.toml`, `package.json`, `pyproject.toml` —
тож вони не можуть розійтися. Вона відхиляє версію, що сортується нижче за
поточну, якщо ви не передасте `--allow-downgrade`, тому що Astra
відмовляється встановлювати пониження версії, і такий реліз був би
невстановлюваним.

Тег зобов'язаний збігатися з `tag-prefix` плюс версія маніфесту, і CI це
перевіряє перш ніж щось збирати. `astra-plugin version` друкує точний тег,
який потрібно використати:

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

## 3 · Що робить CI

Цей розділ описує `.github/workflows/plugin-release.yml`, як він написаний
у цьому репозиторії, на `master`, на коміті, на який вказує
`plugin-release/v1` — тому самому, який викликає ваш `release.yml`.

Три завдання, і цей розподіл і є властивістю безпеки.

| Завдання | Запускає ваш код | Тримає токен на запис | Що робить |
|---|---|---|---|
| **plan** | **ні** | так | Читає `plugin.toml` через `tomllib` Python як *дані*, перевіряє тег == версія, вирішує матрицю збірки, створює чорновий реліз |
| **build** (матриця) | так | **ні** | `astra-plugin check --strict`, `astra-plugin build`, верифікація, розпакування, перевірка нижньої межі glibc і самодостатності бандла TypeScript |
| **publish** | ні | так | Перераховує кожен дайджест сама, пише `SHA256SUMS.txt`, засвідчує, завантажує, знімає чернетку з релізу |

`plan` ніколи не виконує нічого з репозиторію — жодних субмодулів, жодних
облікових даних, збережених у `.git/config`. `build` запускає ваш
`build.rs` і ваші lifecycle-скрипти і не має токена, який можна вкрасти.
`publish` завантажує артефакти, хешує їх сама і засвідчує те, що
захешувала.

Матриця вирішується за мовою вашого плагіна: `linux-x64` + `windows-x64`
для Rust, єдина гілка `noarch` для TypeScript і Python.

### Що потрапляє в реліз

| Артефакт | |
|---|---|
| `<id>-<version>-linux-x64.astraplugin` | по одному на ключ платформи |
| `<id>-<version>-windows-x64.astraplugin` | |
| `<id>-<version>.sigstore.jsonl` | пакет атестації, тож користувач без мережі до GitHub все одно може перевірити |
| `SHA256SUMS.txt` | ті самі дайджести, що записує реєстр |

Реліз стає видимим лише після прикріплення кожного артефакту.

### Атестація вимагає публічного репозиторію

Атестації збірки публікуються в публічний журнал прозорості; у приватному
репозиторії для них потрібен GitHub Enterprise. Workflow визначає видимість
вашого репозиторію і, коли вона не публічна, каже про це в підсумку
завдання і виробляє **незасвідчені** бандли — які реєстр не включить до
каталогу. Це реальне обмеження, і воно падає гучно, а не виробляє реліз, що
виглядає нормально.

### Відтворюваність

`astra-plugin build --reproducible` перевіряє детерміновану упаковку:
відсортовані записи, фіксований mtime, фіксований рівень стиснення. Дві
збірки з тих самих вхідних даних виробляють один sha256. CI запускає
канарку відтворюваності на кожному релізі, що й робить пересбірку третьою
стороною осмисленою.

## 4 · Перевірте самі

Будь-хто може верифікувати реліз, не довіряючи ні Astra, ні реєстру:

<!-- doctest: cli -->
```bash
gh attestation verify dice-roller-0.2.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.2.0-linux-x64.astraplugin
```

`astra-plugin verify` сама читає бандл і друкує, що знайшла:

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

Тут важливі коди виходу, і кожен workflow релізу розгалужується за ними:
**1** означає, що бандл неправильний, **2** означає, що CLI не змогла
відповісти — наприклад, відсутній файл. Формат архіву і що зобов'язаний
відхилити верифікатор — [`spec/bundle-v2.md`](../spec/bundle-v2.md).

## 5 · Потім потрапте до каталогу

Один раз. → [Потрапити до каталогу](get-listed.md).

## Що йде не так

| Симптом | Причина |
|---|---|
| Workflow взагалі не запускається | `on: push: tags:` і `tag-prefix:` розходяться. Глоб, вужчий за префікс, ніколи не спрацює |
| «tag does not match the manifest version» | Виконайте `astra-plugin version <v>` і закомітьте перед тегуванням |
| Збірка під Linux падає на відсутньому заголовку | Встановіть `linux-packages: "libasound2-dev pkg-config"` у викликаючому workflow |
| Бандл не засвідчений | Репозиторій приватний |
| `MODULE_NOT_FOUND` при першому запуску | Залежність TypeScript, яку бандлер не зміг відстежити. CI це перевіряє; подивіться externals бандлера |
| Помилка glibc на машині користувача | Щось в архіві вимагає символ вищий за `GLIBC_2.39`. CI це теж перевіряє |
| `invalid value workflow reference` до старту будь-якого завдання | Закріплення називає коміт, який не несе `plugin-release.yml`. Перезапустіть `astra-plugin init-ci`, щоб перезакріпитися на `plugin-release/v1` |
| Реєстр відхиляє реліз з `E_WORKFLOW_NOT_ALLOWED` | Збірка не запустила закріплений багаторазовий workflow Astra. Перезапустіть `init-ci`, перетегуйте і дайте CI пересобрати |

Детальніше: [діагностика](../6-operate/troubleshooting.md).

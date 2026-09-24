# Підписані документи реєстру — нормативна специфікація

> Переклад. Джерело істини — [docs/en](../../en/spec/registry-index.md); за розбіжності відповідає англійська версія.

**Статус:** нормативно для форматів документів і правил верифікації.
**В силі:** ланцюг підпису, описаний тут, специфікований,
реалізований на обох кінцях і заякорений від початку до кінця — див. §0.1, перш ніж
покладатися на будь-яке речення в цьому файлі як на гарантію безпеки.

Чотири документи, три схеми, одна конструкція підпису:

| документ | рядок схеми | підписаний | копія в цьому репозиторії |
|---|---|---|---|
| `root.json` | `astra.registry.root/1` | **нічим** — це транскрипт ключів, вкомпільованих в Astra | `astra-registry/registry/v1/root.json` |
| `trust.json` | `astra.registry.trust/1` | **кореневим** ключем | публікується поряд з каталогом |
| `index.json` | `astra.registry.index/1` | **ключем індексу**, якому делегує `trust.json` | `astra-registry/registry/v1/index.json` |
| `revocations.json` | `astra.registry.revocations/1` | тим самим ключем індексу | `astra-registry/registry/v1/revocations.json` |

Слова вимог — у дусі RFC 2119.

---

## 0. На що ця ланцюг відповідає, а на що ні

Вона відповідає: *чи це той каталог, який опублікував реєстр Astra, чи
він актуальний, і чи не відкликано в ньому щось?* Це єдине, що робить
закешований запис безпечним для встановлення, тому що запис закріплює
дайджест артефакту, а дайджест не спливає.

Вона **не** відповідає на питання *хто зібрав плагін*. Це робить
атестація збірки GitHub, що перевіряється ботом реєстру при прийомі
(§7), ніколи не демоном. Те, що тримає демон, — це *твердження* реєстру
про автора, закріплене при першому встановленні (TOFU) і прив'язане до
URL завантаження — див. §7.3. Текст інтерфейсу зобов'язаний говорити
«той самий автор, що й раніше», а не «верифікована збірка».

### 0.1 Де зараз ланцюг — прочитайте це в першу чергу

* `astra-registry/registry/v1/root.json` несе `"status": "provisioned"`
  і два ключі Ed25519. Церемонія в `astra-registry/SECURITY.md` §4
  (`tools/keygen-root.sh`) пройшла офлайн 2026-08-11.
* `PRODUCTION_ROOT_KEYS` `astra-daemon` перелічує ті самі два. Копія в
  реєстрі публічна, щоб третя сторона могла їх прочитати без розбирання
  бінарника, і щоб розбіжність між двома була помітна; приватні половини
  ніколи не були на мережевій машині.
* **Кореневий ключ не підписує каталог.** Він підписує `trust.json`,
  який делегує ключу підпису індексу. **Цей документ тепер підписаний.**
  `registry/v1/trust.json` верифікується під `astra-root-2026a`, делегує
  ключу підпису індексу `astra-index-2026a`, і називає коміти
  багаторазового workflow, які бот прийме в атестації збірки — їх два
  відтоді, як тег переїхав 2026-08-19: те, на що вказує
  `plugin-release/v1`, і те, на що він вказував раніше. Власна команда
  реєстру `node
  tools/sign-trust.mjs --verify registry/v1/trust.json` друкує всі три
  факти. Тож `E_TRUST_UNPROVISIONED` більше не спрацьовує при прийомі.
* **Каталог, який отримують клієнти, підписаний цим ключем.** З 2026-09-20
  підписувач реєстру (`astra-registry/.github/workflows/sign.yml`) —
  єдиний видавець того, що читають клієнти. Він підписує `index.json` і
  `revocations.json` ключем `astra-index-2026a`, фіксує їх у гілці
  `signed` і викладає документи цієї гілки на Pages. Перевірено 2026-09-24:
  `index.json`, який віддає Pages, верифікується під `astra-index-2026a`
  проти `trust.json`, що віддається поруч із ним, на серійному номері 52.
  `classify_signature` у демоні розділяє два способи, якими каталог усе ще
  може прийти непідписаним: `NoTrustAnchor` означає, що до збірки не дійшов
  верифікований `trust.json`, тобто немає чим перевіряти підпис;
  `NoSignatures` означає, що якір довіри на місці, а сам каталог не несе
  жодного підпису.
* Копії, зафіксовані в `main` реєстру, — `registry/v1/index.json` і
  `registry/v1/revocations.json` — несуть `"signatures": []` навмисно:
  «непідписано», сказане вголос, там, де відсутній член не можна було б
  відрізнити від вирізаного. Жоден клієнт їх не читає; підписані копії
  лежать у `signed` і на Pages.
* **Список відкликання, який віддає Pages, теж підписаний** — з коміту
  astra-registry `@FLAG7@` (@ARMED_DATE@), що додав
  `policy/pages-withdrawal-list.json`. Оскільки `verify_revocations_document`
  строга (§6.4), демон залишається в `RevocationFreshness::NotEnforced` лише
  доти, доки хоча б раз не отримає список, валідний за підписом. Відтоді він
  застосовує відкликання, до нього застосовується 7-денне блокування з §5.5, і
  назад він не роззброюється.

Усе нижче описує формат і алгоритм, і ніщо з цього не зміниться, коли
приземлиться ланка, що залишилася. Церемонія кореня пройшла, делегування
підписане, а `index.json`, який отримують клієнти, несе підпис у масиві
`signatures`, тож половина ланцюга, що стосується каталогу, несе вагу на
машині користувача, як і половина списку відкликання: Pages віддає
підписаний список.

## 1. Конверт

Кожен підписаний документ має ту саму зовнішню форму:

```json
{
  "$comment": "…free text…",
  "signed":     { "schema": "…", "serial": 1, "…": "…" },
  "signatures": [ { "key_id": "astra-reg-2026a", "sig": "<base64, 88 chars>" } ]
}
```

* **Автентифікований лише `signed`.** Ніщо поза ним не може читатися як
  факт — ні `$comment`, ні рядки `key_id`, ні сама форма списку підписів.
* `sig` — це base64 сирого **64-байтного підпису Ed25519**. Схема
  індексу закріплює написання: `^[A-Za-z0-9+/]{86}==$`.
* `key_id` — це **підказка** для логування і вибору ключа. Верифікатор
  **ЗОБОВ'ЯЗАНИЙ** пробувати кожен довірений ключ проти кожного
  запропонованого підпису і **ЗОБОВ'ЯЗАНИЙ** повідомляти `key_id` ключа,
  який реально верифікував, ніколи не той, що заявив документ. Документ,
  що бреше про те, хто його підписав, все одно верифікується, якщо це
  зробив довірений ключ, і ніколи не верифікується через те, що назвав
  правильний ключ.
* Порожній масив `signatures` означає непідписаність. Це не форма
  помилки; це стан до церемонії і стан будь-якого написаного вручну
  локального каталогу.

## 2. Вхідні дані підпису

```
digest = SHA-256( domain ‖ 0x00 ‖ JCS(signed) )
sig    = Ed25519(private_key, digest)
```

* `domain` — це рядок схеми документа: `astra.registry.trust/1`,
  `astra.registry.index/1`, або `astra.registry.revocations/1`.
* **Верифікатор бере `domain` з власної константи, ніколи з члена
  `schema` файлу, який читає.** Інакше підпис над `trust.json` був би
  відтворюваний як підпис над `index.json` редагуванням одного рядка —
  і будь-хто, хто міг би отримати підпис на один каталог, міг би потім
  опублікувати *порожній* список відкликання і вимкнути механізм.
* `0x00` — це те, що не дає домену, який є префіксом іншого, зіткнутися
  з ним.
* Верифікація Ed25519 **МАЄ** бути строгою (`ed25519_dalek::verify_strict`,
  або еквівалент): відхиляти публічні ключі низького порядку і піддатливі
  кодування, які приймає поблажливий верифікатор.
* Підпис — над дайджестом SHA-256, переданим в Ed25519 як звичайне
  повідомлення. Не вмикайте жодний режим «попереднього хешування»;
  Ed25519 хешує всередині, і ця конструкція подає йому 32 байти.

Обидва кінці цього існують і згодні через тест:
`astra-registry/bot/lib/sign.mjs` (`signingDigest`, `signEnvelope`,
`verifyEnvelope`) і `astra-daemon/src/plugins/trust.rs` (`signing_digest`,
`verify_envelope`). `astra-registry/bot/fixtures/index/` тримає документ,
вироблений JavaScript-підписником, який Rust-верифікатор звіряє
побайтово, тож жоден не може розійтися без червоної збірки.

## 3. Канонізація (профіль JCS)

`JCS(signed)` — це канонічний JSON за RFC 8785, з одним навмисним
звуженням.

* **Ключі об'єкта відсортовані за одиницею коду UTF-16** (RFC 8785
  §3.2.3). Це те, що робить `Array.prototype.sort()` JavaScript за
  замовчуванням, а Rust-сторона виписує це явно
  (`a.encode_utf16().cmp(b.encode_utf16())`), а не покладається на
  байтовий порядок. Для чисто ASCII-ключів ці два порядки збігаються;
  вище BMP — ні.
* **Без незначущих пробілів.** Компактна форма.
* **Рядки** екрануються так, як вимагає RFC 8785 §3.2.2.2: екранувати
  `"`, `\` і керуючі символи C0 (короткими формами, де вони є),
  залишати `/` і весь не-ASCII як буквальний UTF-8.
* **Числа ЗОБОВ'ЯЗАНІ бути цілими в діапазоні ±(2^53 − 1)** —
  `Number.MAX_SAFE_INTEGER` JavaScript. Обидві реалізації
  **відмовляються** від будь-чого іншого, а не реалізують канонізацію
  чисел з рухомою крапкою з §3.2.2. Реєстр видає лише цілі числа
  (`serial`, `size`, `protocol`), і реалізація, що реалізувала §3.2.2
  *майже* правильно, виробляє підписи, що верифікуються з одного боку і
  ні з іншого. `1.0` і `1` — те саме число JSON, і обидва серіалізуються
  як `1`.
* **Дублюючі ключі об'єкта ЗОБОВ'ЯЗАНІ відхилятися при розборі**, а не
  розв'язуватися (RFC 8785 §3.1). `{"a":1,"a":2}` означає дві речі, а
  підписаний документ повинен означати одну. Хвостові байти після
  документа відхиляються з тієї самої причини.
* Членів, чиє значення `undefined`, не існує; в JSON такого немає.
  (Серіалізатор реєстру їх відкидає; JSON-парсер ніколи такого не
  виробляє.)

Гарно відформатований файл, зафіксований у репозиторії, вироблений *тим
самим* серіалізатором (`stableStringify`) з тим самим порядком ключів,
тож рецензент, що читає дифф, читає байти, які підписуються, з точністю
до пробілів.

## 4. Ключі, делегування і ротація

### 4.1 Корені

* Ed25519. Публічні половини **вкомпільовані в Astra**, base64 сирих 32
  байт.
* **Два слоти**, згенеровані на одній офлайн-церемонії: один `Active`,
  один `Reserve`, який ніколи не використовується, поки корінь не
  доведеться замінити. Обидва постачаються з першого дня, тож заміна
  кореня — це підпис, а не день поломки.
* Корінь підписує **лише `trust.json` і нічого більше**. Підпис кореня
  ніколи не з'являється на `index.json`, на `revocations.json`, або на
  бандлі.
* `root.json` — це транскрипт, не повноваження: він непідписаний
  навмисно — самопідписаний кореневий документ не доводить нічого, чого
  вже не доводить вкомпільований ключ. Він існує, щоб можна було
  порівняти дві копії. `fingerprint_sha256` кожного запису — це SHA-256
  над сирим 32-байтним публічним ключем, hex у нижньому регістрі; те
  саме значення друкує `tools/keygen-root.sh` і логує демон, коли підпис
  кореня верифікується.
* Тестові корені існують (`astra-registry/tools/testkeys/`, приватні
  половини зафіксовані навмисно, `key_id` з префіксом
  `TEST-ONLY-DO-NOT-TRUST-`). Демон може вкомпілювати їх лише за
  недефолтною фічею `insecure-test-trust-roots` **у debug-профілі**;
  прохання про це в release-профілі — це `compile_error!`.

### 4.2 `trust.json`

```json
{ "signed": {
    "schema": "astra.registry.trust/1",
    "serial": 3,
    "issued_at": "2026-08-01T00:00:00Z",
    "expires_at": "2026-11-01T00:00:00Z",
    "index_keys": [
      { "key_id": "astra-reg-2026a", "public_key": "<base64 32 bytes>",
        "not_before": "2026-07-01T00:00:00Z", "not_after": "2026-10-01T00:00:00Z",
        "comment": "quarterly" }
    ],
    "reusable_workflow_shas": ["<40-hex commit>"]
  },
  "signatures": [ … ] }
```

Правила верифікації:

* `serial` **НЕ ПОВИНЕН** бути 0 — 0 це сентинель «ще нічого не
  прийнято» на боці верифікатора, тож опублікований документ не може
  його заявляти.
* `schema` **ЗОБОВ'ЯЗАНА** дорівнювати `astra.registry.trust/1`.
  Перевіряйте це до підпису чисто для того, щоб неправильно оформлений
  документ казав «неправильна схема», а не «жоден корінь це не
  підписав»; це не може змінити підсумок, тому що домен дайджеста —
  власна константа верифікатора.
* Невідомі члени **зберігаються й ігноруються**. Новіший реєстр, що
  додає поле, не повинен ламати старіший демон, і сирий верифікований
  `signed` переживає круговий прохід, тож ніщо не відкидається мовчки і
  не підписується заново.
* Запис `index_keys` з нерозбираним ключем або нерозбираним вікном
  **пропускається з попередженням**, а не валить усе: один поганий
  рядок не повинен коштувати каталогу, який міг би верифікувати інший
  ключ. Нерозбираний `not_before` трактується як *ще не дійсний*, а
  нерозбираний `not_after` як *прострочений* — відмова за замовчуванням
  на рівні рядка, відкрито на рівні документа.
* `reusable_workflow_shas` — це список дозволених commit SHA
  багаторазового workflow, який застосовує **бот реєстру** (§7). Демон
  його несе і не використовує. Зміна цього — церемонія кореневого
  ключа, і в цьому весь сенс того, що це лежить тут.

**Ротація.** Щоквартально, і негайно при підозрі. Планова ротація
публікує `trust.json`, у якому у ключа, що виходить, і того, що
приходить, **перекривні вікна на 30 днів**, тож `index_keys_valid_at(now)`,
що повертає два ключі, — це нормальний стан під час переходу, а не
аномалія.

### 4.3 Який годинник судить вікно ключа

Існують два показання годинника: цієї машини, і HTTP `Date` запиту, що
виробив документ.

* **Свіжість** (§5) оцінюється за `now = server_date ?? local` —
  довіряти показанню реєстру на час одного запиту. Це нічого не коштує
  атакуючому, чого в нього вже не було (він міг би віддати застарілий
  документ машині, чий годинник він не контролює), і рятує набагато
  частіший випадок: ноутбук з невірним годинником, якому кажуть, що
  його каталог прострочений.
* **Вікна валідності ключів** оцінюються за
  `window_now = max(local, server)` — мережа може підтягнути «зараз»
  *вперед* і **ніколи** не штовхнути його *назад*. `not_after` — єдиний
  механізм, що виводить з обігу скомпрометований ключ індексу; оцінка
  його за миттю, поставленою мережею, дозволила б злодію також обрати
  день, назавжди, відповідаючи старим `Date`. Взяття пізнішого показання
  робить вкрадений відкликаний ключ *більш* простроченим, яким би
  показанням не керував атакуючий.
* Розбіжність понад **2 години** (`CLOCK_SKEW_TOLERANCE_HOURS`) сама по
  собі є сигналом: вердикт стає `CLOCK_SKEW`, а не твердженням про
  документ. Достатньо мало, щоб мертва батарейка CMOS одразу це
  спровокувала, достатньо велике, щоб звичайний дрейф без NTP цього не
  робив.
* Усе **довговічне**, записане від годинника (мітки часу останнього
  запиту, нижні межі), спершу затискається локальним годинником. Одна
  відповідь з `Date: Fri, 01 Jan 2100 …` інакше пересунула б уявлення
  демона про теперішнє на 2100 рік назавжди — довговічна відмова в
  обслуговуванні, написана будь-ким, хто може відповісти на один запит.

## 5. `index.json`

### 5.1 Форма

`signed` — це:

| член | тип | правило |
|---|---|---|
| `schema` | конст `astra.registry.index/1` | обов'язковий |
| `serial` | ціле ≥ 0 | обов'язковий, монотонний (§5.4) |
| `issued_at` | `YYYY-MM-DDTHH:MM:SSZ` | проставляється **при підписі**, відсутній у зафіксованому дереві |
| `expires_at` | те саме | `issued_at + 30 днів` |
| `plugins` | масив | один запис на кожен заявлений плагін, відсортовано за `id` |
| `publishers` | object, GitHub login → `signed.publishers.<owner>` | optional: one record per account a listing's `publisher` names, and absent when none does |

Часові мітки — RFC 3339 UTC, **точність до секунд, без мілісекунд, без
зсуву**. Два написання однієї миті — це два різні підписані документи.

Запис плагіна несе `id`, `name`, `version`, `description`, `license`,
`capabilities`, `repository_url`, `source`, `icon_url`, `downloads`,
`stars`, `updated_at`, `download_url`, `platform_downloads` і
`releases[]`. Повна JSON Schema — `astra-registry/schema/index-v1.json`;
у неї `additionalProperties: false`, і вона — авторитет щодо списку
полів.

Два правила варто повторити, тому що верифікатор залежить від них:

* **`releases[]` — авторитетна половина**, спершу найновіші за
  прецедентом semver. У кожного релізу є `version`, `published_at`,
  `release` (`{kind: "github_release", repo, tag}` або
  `{kind: "direct", base_url}`) і `artifacts` (ключ платформи →
  `{url, filename, sha256, size}`).
* **Плоскі поля — це проєкція** `releases[0]`, обчислювана тим самим
  проходом генератора, тож вони не можуть з ним розійтися. `version`,
  `platform_downloads` і `download_url` існують, тому що демон в
  постачанні читає рівно їх.

Ключі платформи: `linux-x64`, `windows-x64`, `noarch`, плюс
зарезервовані `linux-arm64`, `windows-arm64`, `macos-x64`,
`macos-arm64`. Артефакт `noarch` записується під **кожним підтримуваним
ключем платформи**, тож жодному клієнту не треба знати це слово
(`PLATFORM_KEYS_FOR_NOARCH = ["linux-x64", "windows-x64"]`).

`downloads` і `stars` завжди `0`. Цей реєстр нічого не рахує.

**Стейджингові записи** — заявка, чий реліз існує на папері, але ще без
дайджеста артефакту, — позначені `staging: true`, **опущені з
`platform_downloads` і `download_url`**, і невстановлювані за
побудовою: немає дайджеста — немає встановлення.

> **These tables are in English in every language.** The `publishers` row of the
> table above and every table below are the English page's, copied as they are:
> they document `astra-registry/schema/index-v1.json` member for member, C21 in
> `tools/check-registry-mirrors.py` holds the English page to that file, and nobody
> on this side can review a translation of them. Each table is one object, named in
> the line above it; a rule begins with *required*, *optional* or *required when*,
> which are the schema's `required` lists. A translation is welcome; English stays
> authoritative either way.

A plugin record, `signed.plugins[]`, is:

| member | type | rule |
|---|---|---|
| `id` | string, 2–64 characters of `a-z`, `0-9` and `-`, beginning and ending with a letter or digit | required: the listing's directory name in the registry; records are sorted by it |
| `name` | string, 1–64 characters | required: the card's title, in English |
| `version` | string | required: the latest listed release, `releases[0].version` |
| `description` | string, ≤ 200 characters | required: the one-line card text, in English — `plugin.json`'s `summary`, under the name the daemon already reads. It is not `plugin.json`'s own `description`, which the index does not carry |
| `i18n` | object, locale code → `signed.plugins[].i18n.<code>` | optional: the card in other languages, read out of the attested bundle's `locales/<code>.json`. The codes are `ru`, `uk`, `de`, `fr`, `es`, `pt`, `ja`, `zh` and `ko`; `en` is never one, because `name` and `description` are the English. A client that does not read this member renders English |
| `readme` | string, ≤ 16384 characters | optional: the plugin's own README, inlined so the signature covers it and opening the store asks no third party for anything. GitHub-flavoured markdown with no raw HTML and no image outside GitHub's asset hosts. The registry's own cap is 16384 UTF-8 **bytes** (`MAX_README_BYTES`), and the schema's character bound is its backstop. Absent when the plugin ships no README |
| `author` | string, ≤ 64 characters | optional: `plugin.json`'s `author.name` — whatever the author typed, not an identity the registry proves (that is `publisher`) |
| `author_url` | string, `^https://` | optional: `plugin.json`'s `author.url` |
| `license` | string, ≤ 64 characters | required: `plugin.json`'s `license`, which `tools/validate.mjs` holds to `policy/spdx-allowlist.json` |
| `capabilities` | array of unique strings | required: `releases[0].capabilities`, or `[]` when that release declares none |
| `categories` | array of unique strings | optional: `plugin.json`'s `categories`, sorted |
| `keywords` | array of unique strings | optional: `plugin.json`'s `keywords`, sorted |
| `homepage` | string, `^https://` | optional: `plugin.json`'s `homepage` |
| `repository_url` | string, `^https://github\.com/` | required: `https://github.com/` followed by `source.repo` |
| `icon_url` | string: a `data:image/…;base64,…` URI, or empty | required: the store card's picture, inlined from the icon committed beside the listing so that it is inside the signature; the empty string when there is none. Never an `https://` URL |
| `source` | object, `signed.plugins[].source` | required: where the bytes come from |
| `downloads` | integer ≥ 0 | required: always `0` |
| `stars` | integer ≥ 0 | required: always `0` |
| `updated_at` | `YYYY-MM-DDTHH:MM:SSZ` | required: `releases[0].published_at` |
| `added_at` | `YYYY-MM-DD` | optional: the day the plugin was first listed. `schema/plugin-v1.json` requires it of every listing, and the generator copies it through |
| `staging` | boolean | optional: `true` when the latest listed release has no artifact digest yet (*Staging entries*, above); never written as `false` |
| `download_url` | string | required: the legacy platform-agnostic URL. Empty except for an installable `noarch` release, which has one artifact for every host |
| `platform_downloads` | object, platform key → `https://` URL | required: the projection of `releases[0].artifacts`. `{}` when that release is not installable — staging, or any artifact without both `sha256` and `size` |
| `releases` | array of `signed.plugins[].releases[]`, at least one | required: newest first by semver precedence. A yanked version is not listed |
| `publisher` | string | optional: the key into `signed.publishers` — the login of the reviewed publisher record that the owner half of `source.repo` resolves to, case-insensitively, as that record's own login or one it `covers`. **Absent** when no reviewed record exists, and the absence is the answer: a client that badges on this member being present badges every listing. Never the `author` string |

The card in one other language, `signed.plugins[].i18n.<code>`, is:

| member | type | rule |
|---|---|---|
| `name` | string, 1–64 characters | required: the card's title in that language, from the locale's `listing.name` |
| `description` | string, 1–200 characters | required: the one-line card text in that language, from the locale's `listing.description`. A half the locale does not translate is filled from English, so a block always has both, and a block identical to the English card is left out |

Where a plugin's bytes come from, `signed.plugins[].source`, is:

| member | type | rule |
|---|---|---|
| `kind` | const `github` | required |
| `repo` | string, `owner/name` | required: the GitHub repository the plugin is published from. `repository_url` is built from it, and `publisher` is resolved from its owner half |
| `subdirectory` | string | optional: copied through from `plugin.json`'s `source.subdirectory` |

One release, `signed.plugins[].releases[]`, is:

| member | type | rule |
|---|---|---|
| `version` | string | required: this release's semver version |
| `published_at` | `YYYY-MM-DDTHH:MM:SSZ` | required: the GitHub Release's publication time, recorded in the version file rather than read from a clock |
| `protocol` | integer, 0–65535 | optional: the plugin protocol version the bundle speaks |
| `min_astra_version` | string | optional: the lowest Astra version the plugin's manifest says it needs |
| `capabilities` | array of unique strings | optional: the daemon's capability names, verbatim, sorted |
| `permissions` | object | optional: the manifest's `[permissions]` section, copied through unchanged. The one open object in this document (`additionalProperties: true`): its ids are the app's vocabulary, so an id this schema has never heard of is carried rather than refused. `schema/version-v1.json` says what the daemon reads from it |
| `changelog_url` | string, `^https://` | optional: copied through from the version file |
| `staging` | boolean | optional: `true` on a release that exists on paper and has no artifact digest yet; never written as `false` |
| `staging_reason` | string | optional: written only beside `staging: true`, copied through from the version file |
| `release` | object, `signed.plugins[].releases[].release` | required: where the artifacts are served from, which is what their URLs must sit under (§5.2) |
| `artifacts` | object, platform key → `signed.plugins[].releases[].artifacts.<platform>`, at least one | required |

Where a release is served from, `signed.plugins[].releases[].release`, is:

| member | type | rule |
|---|---|---|
| `kind` | `github_release` or `direct` | required |
| `repo` | string, `owner/name` | required when `kind` is `github_release`: the repository whose release serves the artifacts |
| `tag` | string | required when `kind` is `github_release`: that release's tag |
| `commit` | string, 40 lowercase hex digits | optional: the source commit that built the artifacts, recorded at ingest. The bot refuses a Release whose commit disagrees with its build attestation's |
| `base_url` | string, `^https://` | required when `kind` is `direct`: the prefix every artifact URL of this release sits under. Policy keeps `direct` out of the public catalogue (§5.2) |

One artifact, `signed.plugins[].releases[].artifacts.<platform>`, is:

| member | type | rule |
|---|---|---|
| `url` | string, `https://`, ≤ 1024 characters | required: where the file is downloaded from. It must sit under the prefix its release implies and end in `filename` (§5.2) |
| `filename` | string, ending `.astraplugin` | required |
| `sha256` | string, 64 lowercase hex digits | optional: the SHA-256 of the whole `.astraplugin` file (§5.2). Absent only on a staging release, which is uninstallable by construction |
| `size` | integer, 1 byte to 256 MiB | optional: that file's length in bytes (§5.2) |

A publisher record, `signed.publishers.<owner>`, is what the registry knows about the account behind a listing, keyed by that account's GitHub login. It is inside `signed`, so the signature a client already checks covers it — a badge is a claim the registry makes, and a claim outside the signature is one whoever serves the bytes could invent:

| member | type | rule |
|---|---|---|
| `display_name` | string, 1–64 characters | required: what a person sees beside the badge |
| `description` | string, 1–120 characters | optional: one line saying who this publisher is to Astra. A client renders nothing when it is absent rather than inventing a default |
| `tier` | `astra_team` or `verified` | required: a client **MUST** render on explicit membership — equal to `astra_team` or equal to `verified` — and never on the value merely being present or non-empty. An unrecognised tier is not a badge |
| `verified_at` | `YYYY-MM-DD` | required: when the evidence behind the tier was first accepted |
| `last_confirmed_at` | `YYYY-MM-DD` | optional: when that evidence last held |

### 5.2 Дайджест артефакту, і куди можуть вказувати URL

`artifacts.<key>.sha256` — це `sha256` усього файлу `.astraplugin` — те
саме число, що і предмет атестації, і те, що хешує демон
([`bundle-v2.md` §3.1](bundle-v2.md#31-дайджест-артефакту)). `size` — це
довжина цього файлу; схема обмежує її 256 МіБ.

Кожен URL артефакту **ЗОБОВ'ЯЗАНИЙ** бути `https://` і **ЗОБОВ'ЯЗАНИЙ**
лежати під префіксом, який передбачає його власний об'єкт `release`:

* `github_release` → `https://github.com/<repo>/releases/download/<tag>/`,
* `direct` → `base_url` релізу,

і **ЗОБОВ'ЯЗАНИЙ** закінчуватися оголошеним `filename`. Це
застосовується в `astra-registry/tools/validate.mjs`, не паттерном
схеми, тому що паттерн, здатний описати лише GitHub, робив би
самостійно розміщений випадок невиразним. `direct` існує для самостійно
розміщених і стейджингових каталогів; політика тримає його поза
публічним каталогом.

### 5.3 Детермінізм — властивість, на яку спирається аудитор

Член `signed` `index.json` генерується з `plugins/**` через
`tools/build-index.mjs` і **не читає годинник**: ті самі джерела + той
самий serial → ті самі байти. Ключі відсортовані за одиницею коду
UTF-16, плагіни за id, релізи за semver. `--check` валиться, якщо
зафіксований файл відрізняється хоч на байт, і CI це запускає.

`issued_at`/`expires_at` додаються `bot/sign-index.mjs` під час підпису,
а не генератором, з двох причин: вони — властивості *публікації*, а
генератор, що читає годинник, неможливо було б відтворити. Саме це
робить аудит з §8 взагалі можливим — третя сторона може пересобрати
вміст каталогу з дерева git і порівняти його з тим, що було підписано.

### 5.4 Serial

* **Монотонний**, виведений з `git rev-list --count HEAD -- plugins` на
  дефолтній гілці. Ніколи не прочитаний-і-інкрементований з файлу: два
  злиття в ту саму хвилину обидва читають *N* і обидва пишуть *N+1*, і
  друге мовчки скасовує збільшення першого. Число комітів — властивість
  історії, тож паралельні злиття отримують різні значення за побудовою.
  Обмеження за шляхом означає, що коміт у документацію не зсуває номер
  версії каталогу.
* Верифікатор тримає **нижню межу serial** на каталог URL і відхиляє
  все нижче неї. Межа — `max(в пам'яті, на диску)` і живе в стані, яким
  володіє демон, з MAC (`astra.registry.state/1`), **не** в кеші
  індексу: кеш — це зручність, яку можна видалити в будь-який момент, а
  межа — рішення безпеки, яке зобов'язане пережити саме те видалення,
  яке б скоїв атакуючий. Вона монотонна *в коді*, тож псування файлу
  стану скидає файл, а не працюючий процес.

Три документи, три правила serial, і відмінності навмисні:

| документ | приймається коли | чому |
|---|---|---|
| `trust.json` | **строго більший**, ніж утримуваний | він змінюється лише при ротації ключа, тож «той самий serial, інші байти» — спроба відкату і нічого більше |
| `index.json` | **не нижче** межі | звичайна переопублікація |
| `revocations.json` | **більший або рівний** на диску; **строго більший** serial замінює набір, менший-або-рівний може лише **додавати** | список підписується заново за розкладом, щоб залишатися всередині свого 7-денного вікна; відмова від рівного заблокувала б встановлення в кожен тихий тиждень. «Той самий serial, менше записів» — це replay, а лише-додавання це перемагає |

MAC на файлі стану — це **розтяжка, не межа**: ключ живе в тому самому
каталозі 0700, що і файл, який він автентифікує, тож атакуючий, здатний
читати цей каталог, може його підробити. Це піднімає планку з
«відредагувати файл» до «знайти і використати ключ». Справжня межа — це
каталог — сусідній з `plugins/`, ніколи не нащадок, тож суб'єкт цих
рішень не є також їхнім автором.

### 5.5 Свіжість, і асиметрія, яка важливіша за все

| документ | TTL | чого коштує застарілість |
|---|---|---|
| `index.json` | **30 днів** (`CATALOG_TTL_DAYS` / `CATALOG_MAX_AGE_DAYS`) | **банер**. Перегляд каже, що каталог старий. **Закешовані, закріплені за дайджестом записи залишаються встановлюваними.** |
| `revocations.json` | **7 днів** (`REVOCATION_TTL_DAYS` / `REVOCATION_MAX_AGE_DAYS`) | **жорсткий блок** нових встановлень |

Ця асиметрія — вся політика свіжості, і вона випливає з того, для чого
призначений кожен документ. Запис каталогу — це *дайджест*, а дайджест
не спливає: атакуючий, що заморожує реєстр так, щоб ви тримали запис,
який уже верифікували, нічого не виграє. Список відкликання —
протилежність — «продовжувати» там означає «продовжувати встановлювати
те, що ми, можливо, вже відкликали» — тож цей блокує:

> `REVOCATIONS_STALE: Astra can't check whether this plugin has been withdrawn.
> The withdrawal list it has is N days old and Astra will not install with one
> older than 7 days. Reconnect to the network and try again. Plugins already
> installed keep running.`

Зверніть увагу на останнє речення. Застарілість ніколи не зупиняє вже
працюючий плагін.

Коди вердиктів, які видає верифікатор, що відповідає специфікації, від
найсерйознішого (`IndexVerdict::code`):

| код | значення |
|---|---|
| `SIGNATURE_INVALID` | підписи були запропоновані, і жодна не зроблена довіреним ключем. **Єдиний код, що означає підробку.** Годинник не бере участі в приході до нього, тож жоден годинник не може його виправдати. |
| `SIGNATURE_KEY_EXPIRED` | делегований ключ підписав його поза своїм вікном, оцінено з серверним `Date` в руках (тож розбіжність годинника — не виправдання) |
| `CLOCK_SKEW` | годинник цієї машини і часові мітки документа не можуть бути правильні обидва, а підпис верифікувався — тож підозрюється годинник |
| `CATALOG_STALE` | після `expires_at` |
| `FRESHNESS_UNKNOWN` | немає `issued_at` і немає `expires_at` — написаний вручну локальний каталог |
| `UNSIGNED` | немає підписів, або немає якоря довіри, проти якого їх перевіряти |

`SIGNATURE_INVALID` і `SIGNATURE_KEY_EXPIRED` — це **відмови**: документ
взагалі не читається, і для нього не пропонується закешований відкат.
`UNSIGNED` — не відмова — це стан світу до церемонії і стан будь-якого
локального каталогу — але він ніколи не може підвищити запис до повністю
довіреної.

Звідки документ був **отриманий, ніколи не є вхідним параметром**.
Каталогу вірять, тому що його підписав делегований ключ;
`plugins.registry_url` — це звичайна конфігурація, і від каталогу
очікується, що він буде переїжджати між хостами. Шлях верифікації
демона не містить перевірки імені хоста і не повинен її набути.

## 6. `revocations.json`

### 6.1 Форма

```json
{ "signed": {
    "schema": "astra.registry.revocations/1",
    "serial": 12,
    "issued_at": "…", "expires_at": "…",
    "revocations": [
      { "kind": "digest", "value": "<64 hex>",
        "id": "ASTRA-2026-0001", "severity": "critical", "action": "disable",
        "reason": "Exfiltrated conversation history to an attacker-controlled host.",
        "advisory_url": "https://…" }
    ] },
  "signatures": [ … ] }
```

Згенеровано з одного файлу на рекомендацію під
`astra-registry/tools/revocations/` через `tools/build-revocations.mjs`;
одна рекомендація стає одним записом на кожен ключ, який вона називає, і
кожен запис несе id рекомендації, серйозність, дію, причину і URL, тому
що клієнт показує рівно одну з них — першу, що збіглася, — і кожна
повинна стояти сама по собі. Записи відсортовані за `(kind, value)`, тож
документ детермінований.

### 6.2 Словник видів

`RevocationKind` у `astra-daemon/src/plugins/trust.rs` — авторитет;
таблиця `KINDS` реєстру існує, щоб реєстр не міг опублікувати вид, який
демон мовчки проігнорував би — невідомий вид — це відкликання, яке не
відбувається.

| вид | `value` | збігається з |
|---|---|---|
| `digest` | 64 hex у нижньому регістрі | `sha256` усього `.astraplugin`, порівнюється без урахування регістру |
| `binary` | 64 hex у нижньому регістрі | `sha256` **розв'язаного файлу `entry.command`** |
| `id` | id плагіна | кожна версія цього плагіна |
| `id_version` | `<id>@<semver>` | рівно той реліз |
| `version_range` | id плагіна + вікно `versions` | див. §6.3 |
| `identity` | `github:owner/repo` або `origin:host` | закріплена ідентичність видавця |
| `publisher_key` | id ключа | `signer_key_id` запису довіри |

`action` — це `block_install`, `disable` або `warn`. `warn` не блокує
встановлення; `disable` також зупиняє і вимикає вже встановлену копію.
`severity` (`critical` / `high` / `moderate` / `low`) — лише
рекомендаційна — поведінка від неї не залежить.

`reason` показується користувачу **дослівно** у сповіщенні, яке демон
позначає постійним, тож генератор відхиляє текст, що містить
bidi-перевизначення або з'єднувачі нульової ширини, і обмежує його 300
символами.

### 6.3 Вікна версій

Форма і семантика OSV: `introduced` **включна**, `fixed`
**виключна**, обидва опціональні, а `{}` означає кожну версію — що
робить `version_range` строгим узагальненням `id`. `introduced == fixed`
не покриває нічого і відхиляється при збірці.

Порядок — стандартний прецедент semver, тож `1.0.0-rc.1 < 1.0.0`:
рекомендація, що каже «виправлено в 1.0.0», не повинна залишати
`1.0.0-rc.1` невідкликаним. Метадані збірки ігноруються (semver §10).
**Рядок версії, який жодна сторона не може розібрати, знаходиться
*всередині* вікна** — альтернатива в тому, що `version = "totally-fine"`
прослизнула б повз кожну межу, яку могла б виразити рекомендація, і
атакуючий обирає цей рядок.

### 6.4 Верифікація строга, на відміну від каталогу

`verify_index_document` повертає градуйований вердикт;
`verify_revocations_document` повертає `Err`. Відсутність якоря довіри,
відсутність підпису, підпис від стороннього, або підпис від ключа поза
своїм вікном — усе це провали. До списку відкликання звертаються лише
для того, щоб щось *відхилити*, тож документ, який ніхто не може
атрибутувати, має рівно одне безпечне прочитання — «це не список
відкликання» — і повернення його як порожньої множини було б бажаним
підсумком для атакуючого, досяжним віддачею взагалі будь-якого файлу.

Відсутність придатного списку обробляється на рівень вище, 7-денним
блоком (§5.5). Саме це, а не поблажливий парсер, не дає простою реєстру
стати тихою втратою застосування.

Закешований список **перевіряється заново при кожному завантаженні**,
ніколи не довіряється тому, що цей демон одного разу його написав, —
саме це дозволяє закешованій копії бути вхідними даними рівня
встановлення, і саме тому ротація ключа виводить з обігу закешований
список у той самий момент, що й живий.

### 6.5 Діра сайдлоаду, закрита біля джерела

Рекомендація лише за дайджестом за замовчуванням залишає діру: відкличте
за дайджестом, і користувач може видалити (скинувши запис довіри, з
якого був прочитаний дайджест), скопіювати `plugin.toml` і бінарник в
каталог, і сайдлоаднути той самий код. У каталогу немає архіву, тож у
нього немає дайджеста бандла і немає підписанта.

Генератор тому **відхиляє рекомендацію, у якої кожен запис закріплений
на чомусь, чого в каталогу бути не може.** Хоча б один запис
**ЗОБОВ'ЯЗАНИЙ** бути виду `binary`, `id`, `id_version` або
`version_range`. `identity` і `publisher_key` явно не рахуються.

П'ять точок застосування споживають список: встановлення (§5.3-A.4
плану), розв'язання оновлення, шлях імпорту, шлях сайдлоаду, і
періодичний перетин списку з встановленими плагінами за записаним
`artifact_sha256`.

## 7. Походження — що перевіряє реєстр, чого демон не може

### 7.1 При прийомі (бот реєстру, `bot/lib/attestation.mjs`)

1. `gh attestation verify <file> --repo <repo> --signer-workflow <path>
   --format json`. Це доводить, що workflow в цьому репозиторії зібрав
   ці байти і що Sigstore це записав.
2. **Дайджест предмета атестації ЗОБОВ'ЯЗАНИЙ дорівнювати `sha256`
   артефакту** — третє з трьох місць цього числа
   (`E_ATTESTATION_SUBJECT_MISMATCH`).
3. Вихідний репозиторій сертифіката ЗОБОВ'ЯЗАНИЙ бути
   `https://github.com/<repo>` (`E_ATTESTATION_REPO_MISMATCH`).
4. **Розв'язаний commit SHA багаторазового workflow** зчитується назад
   з сертифіката і ЗОБОВ'ЯЗАНИЙ з'являтися в `reusable_workflow_shas`
   `trust.json` (`E_WORKFLOW_NOT_ALLOWED`). Відсутній SHA — це провал,
   не значення за замовчуванням (`E_ATTESTATION_INVALID`).

Крок 4 — це те, що робить змінний тег `@v1` непридатним як ланцюг
постачання: тег можна перенацілити на будь-який коміт, а атестація
все одно називатиме правильний репозиторій і файл workflow. Зміна цього
списку дозволених — церемонія кореневого ключа.

Цей список дозволених тепер існує: відтоді, як тег переїхав 2026-08-19,
підписаний `trust.json` називає два коміти — той, на який вказує
`plugin-release/v1`, і той, на який він вказував раніше, — а ця сторінка не
називає жодного: SHA, скопійований у специфікацію, це копія віддаленого
репозиторію, яку ніхто не звіряє. Тож
`E_TRUST_UNPROVISIONED` більше не зупиняє прийом, і крок 4 в силі —
збірка, вироблена будь-яким іншим workflow, відхиляється з
`E_WORKFLOW_NOT_ALLOWED`. Половина на боці демона все ще відмовляє за
замовчуванням з іншої причини: сам каталог не несе підпису (§0.1).

### 7.2 Не реалізовано: контрпідпис за реліз

`PRODUCTION_PLAN` §5.2 специфікує контрпідпис за реліз над

```
SHA256("astra-registry-countersign-v1" ‖ 0x00 ‖ id ‖ 0x00 ‖ version ‖ 0x00 ‖ platform ‖ 0x00 ‖ artifact_sha256)
```

**Ніщо сьогодні це не обчислює і не перевіряє.** Цей рядок з'являється в
плані і ніде в жодному з трьох репозиторіїв. Автентичність запису
сьогодні приходить з підпису конверта індексу, що покриває весь
каталог. Не реалізуйте верифікатор проти цього розділу, очікуючи
знайти таке поле.

### 7.3 Що робить демон натомість

Демон не виконує **жодної** верифікації Sigstore: атестації
перевіряються в CI бота, де існують мережа, API GitHub і `gh`. Локально
він робить дві речі, і їхнє поєднання — це те, що обмежує компрометацію
ключа реєстру «публікацією нових плагінів»:

* **TOFU-закріплення.** При першому встановленні він записує
  ідентичність, яку заявила заявка (`{kind: "github", repo}` або
  `{kind: "origin", host}`). Оновлення, чия ідентичність відрізняється,
  — **жорсткий блок без обходу, ніколи**.
* **Прив'язка URL-до-ідентичності.** URL артефакту зобов'язаний лежати
  під простором релізів закріпленого репозиторію, порівнюваним за
  хостом і префіксом шляху після розв'язання редиректу. Ідентичність —
  це репозиторій, який **заявляє** запис, ніколи репозиторій, що
  мається на увазі URL, — виведення його з URL зробило б перевірку
  тавтологічною при першому встановленні.

Залишковий ризик, названий, тому що інтерфейс не повинен перебільшувати:
`identity` — це рядок, який стверджує реєстр. Скомпрометований ключ
індексу може опублікувати запис з правдивою ідентичністю і
сфабрикованим блоком походження. Перевірка URL змушує байти приходити з
простору релізів закріпленого репозиторію; компрометація репозиторію
плюс реєстру перемагає обидва.

## 8. Процедура аудиту

Усе в опублікованому каталозі перевірюване третьою стороною без
доступу до жодного приватного ключа. Це процедура. Кроки, позначені
**інструмент**, мають скрипт в `astra-registry`; кроки, позначені
**вручну**, поки ні, і `registry/tools/audit-index.sh`, названий у
`PRODUCTION_PLAN` §5.5, **сьогодні не існує** — він описаний тут як
процедура, яку він автоматизує.

**A. Відтворити вміст каталогу.** *(інструмент)*

```sh
git clone <registry repo> && cd astra-registry
node tools/build-index.mjs --check          # byte-identical regeneration
node tools/build-revocations.mjs --check
node tools/validate.mjs                     # schema + URL pinning + digests
```

Потім порівняйте опублікований член `signed` з регенерованим,
ігноруючи лише `issued_at` і `expires_at` (§5.3). Будь-яка інша різниця
— це каталог, що не збігається з власною історією git.

*Що це друкує сьогодні* (перевірено під час написання цього документа):
обидва запуски `--check` повідомляють «побайтово ідентично свіжій
генерації» на serial 1 з 0 підписами, а `validate.mjs`
**провалюється** — усі одинадцять заявок є стейджинговими записами без
дайджеста артефакту, що вона відхиляє, якщо не переданий
`--allow-staging`. Це правильна відповідь для каталогу, чиї плагіни ще
не випущені, і це причина, чому ніщо в ньому не встановлюване.

**B. Перевірити ланцюг підпису.** *(інструмент)*

```sh
node bot/sign-index.mjs --verify registry/v1/index.json --trust registry/v1/trust.json
```

і, вручну, що `trust.json` верифікується під ключем з
`registry/v1/root.json`, чий відбиток збігається з тим, що логує ваш
бінарник Astra. Перерахуйте незалежно, якщо волієте:
`SHA-256(domain ‖ 0x00 ‖ JCS(signed))`, Ed25519-верифікуйте, згідно з
§2–§3.

*Що це друкує сьогодні:* `FAIL … no trusted key was supplied (offered:
none; trusted: none)` — немає `trust.json`, який можна передати, і
немає кореня, яким можна його верифікувати (§0.1). Верифікатор, що
повідомляє щось інше проти поточного дерева, брехав би.

**C. Перевірити serial і вікно.** *(вручну)* `serial` зобов'язаний бути
≥ останнього, що ви бачили; `expires_at − issued_at` зобов'язана бути 30
днів для каталогу і 7 для списку відкликання; `key_id` зобов'язаний
бути ключем, названим `trust.json`, з вікном, що містить `issued_at`.

**D. Перевірити кожен артефакт проти публічного журналу прозорості.**
*(вручну)* Для кожного релізу в індексі — `<…>` є заповнювачами,
зчитуваними з запису індексу, тож ці дві команди — шаблон, а не
копіпаста:

```sh
curl -fL -o a.astraplugin "<artifacts.<key>.url>"
sha256sum a.astraplugin                     # must equal artifacts.<key>.sha256
gh attestation verify a.astraplugin \
   --repo <release.repo> \
   --signer-workflow <AstraPlugins>/.github/workflows/plugin-release.yml \
   --format json
```

`--repo` — це репозиторій **автора**, з `release.repo` запису індексу.
`--signer-workflow` — це **спільний багаторазовий** workflow, який його
зібрав — той, до якого `astra-plugin init-ci` закріплює того, хто
викликає, утримуваний ботом як `DEFAULT_SIGNER_WORKFLOW` в
`astra-registry/bot/ingest.mjs` і звірюваний з файлом, що існує в
`AstraPlugins/.github/workflows/`. Візьміть точний рядок з цієї
константи, а не відновлюйте його самі; переставлений шлях не збіжиться
з жодною атестацією взагалі, і кожен чесний артефакт тоді
виглядатиме так, ніби її в нього немає.

`gh attestation verify` забирає пакет Sigstore для цього дайджеста
артефакту і звіряє його проти кореня довіри Sigstore, **включно з
доказом включення в журнал прозорості Rekor**. З його JSON-виводу
вручну затвердіть те, що бот затверджує при прийомі (§7.1): дайджест
предмета дорівнює дайджесту файлу, вихідний репозиторій — це
репозиторій, який називає індекс, і розв'язаний commit SHA
workflow-підписанта входить у `reusable_workflow_shas` `trust.json`.

Запис, який реєстр опублікував для артефакту **без** атестації, або
чия атестація називає інший репозиторій, — це рівно те виявлення
постфактум, для якого існує ця процедура: ніщо не заважає
скомпрометованому ключу реєстру опублікувати *новий* плагін, і
можливість аудиту — це вся суть пом'якшення.

**E. Перевірити сам бандл.** *(інструмент)* Запустіть
[`bundle-v2.md` §13](bundle-v2.md#13-алгоритм-верифікації) над
завантаженим файлом, і підтвердіть, що його `MANIFEST.json` —
`plugin_id`, `version`, `platform` і `permissions_hash` — збігаються з
записом індексу.

## 9. Підсумок того, що в силі сьогодні

| властивість | статус |
|---|---|
| формати документів, конверт, конструкція підпису, профіль JCS | реалізовано на обох кінцях, перехресно протестовано фікстурою |
| кореневі ключі | **видані** 2026-08-11 — ті самі два з обох боків |
| `trust.json` | **підписаний** під `astra-root-2026a`, делегує `astra-index-2026a` і допускає один коміт workflow |
| підписи `index.json` / `revocations.json` | порожні масиви в зафіксованому дереві — **це тепер відсутня ланка** |
| вердикти каталогу, нижні межі serial, свіжість, обробка годинника | реалізовано в демоні і покрито тестами |
| словник відкликання, зіставлення, п'ять точок застосування | реалізовано; **бездіє, поки список, валідний за підписом, не буде отриманий хоча б раз** |
| перевірка атестації збірки при прийомі | реалізовано і в силі; список дозволених workflow приходить з підписаного `trust.json` |
| контрпідпис за реліз | специфікована лише в плані; **реалізації немає** |
| `audit-index.sh` | не існує; §8 — ручна процедура |

---

*Джерела, перевірені під час написання цього документа:
`astra-registry/schema/{index-v1,version-v1,plugin-v1}.json`;
`astra-registry/tools/lib/canonical.mjs`; `astra-registry/tools/lib/revocations.mjs`;
`astra-registry/tools/build-index.mjs`; `astra-registry/bot/lib/sign.mjs`;
`astra-registry/bot/sign-index.mjs`; `astra-registry/bot/lib/attestation.mjs`;
`astra-registry/registry/v1/{root,index,revocations}.json`;
`astra-registry/SECURITY.md`;
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/registry_client.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/manager.rs` (`refresh_revocations`).*

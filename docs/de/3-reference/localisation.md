> **Noch nicht übersetzt.** Diese Seite gibt es bisher nur auf Englisch. Bei Abweichungen ist [`docs/en`](../../en/3-reference/localisation.md) maßgeblich.
>
> This page is normative and nobody on this side can review a translation of it, so it ships in English in every language rather than in six versions nobody can check. A translation is welcome; English stays authoritative either way.

# Localisation

Astra can be set to ten languages. A plugin ships **one flat JSON file per
language**, beside `plugin.toml`:

<!-- doctest: illustrative reason="a directory listing, not a program; `astra-plugin new` produces this layout and `astra-plugin locale add` extends it" -->
```
my-plugin/
  plugin.toml
  locales.lock.json      ← at the root, NOT inside locales/
  locales/
    en.json              ← mandatory once locales/ exists
    ru.json
  src/ …
```

<!-- doctest: json -->
```json
{
  "listing.name": "Chess",
  "listing.description": "Play chess against a local bot or an Astra model",
  "config.engine_path.title": "Engine path",
  "config.engine_path.description": "Path to a UCI engine binary. Leave it empty to play the built-in bot.",
  "msg.done.one": "Handled {n} item",
  "msg.done.other": "Handled {n} items"
}
```

**Flat, and every value a string.** This is not a house style. The daemon
deserialises the file into a string→string map, and a nested object or a number
value fails that parse and drops **the whole file**, silently, at install time.
`astra-plugin check` refuses the shape before it can ever get that far, which is
the only reason you will not meet this failure.

`locale add` writes the file for you and never writes anything else, so the
shortest advice is: do not hand-write one.

---

## 1 · Two planes, and the store card

Three different things want translating, and they are resolved by three
different processes. Which one a string belongs to decides how you write it.

| | Rendered by | You write |
|---|---|---|
| **Declared** — config-field titles and descriptions, dropdown option labels, `[ui]` contribution labels | the **daemon**, per request, from the copy of `locales/` it loaded when it installed you | `"$config.engine_path.title"` |
| **Runtime** — chat text, notifications, anything with a count in it | your **own process**, at the moment it produces the string | `ctx.i18n().t("msg.sent")` |
| **The store card** — the name and one-line summary a user reads before installing | the **registry**, out of the bundle it already holds | two reserved keys, below |

The third row is the one to read the small print on, because it is the only one
your own machine never renders: those two keys are read in another repository,
out of the bundle, after you have pushed a tag. See below.

The split is not a preference either. When the store card is drawn there is no
bundle on disk and no process to ask. When a settings form is drawn your process
may not be running. And when your plugin sends a chat message, the daemon cannot
know how many items you handled.

The declared plane is the one worth understanding, because it is the one that
keeps working while you do nothing: you emit a key once, and every language the
user switches to is resolved downstream, with no hook to implement and no
re-render to get right.

### The store card's two keys

`listing.name` and `listing.description` are **reserved, and they are the only
two**: any other `listing.` key is an error. Their English values must equal
`plugin.toml`'s `name` and `description` — that duplication is checked rather
than tolerated, and `astra-plugin locale sync` is the one command that resolves
it, because the two are by definition a copy.

**What they do.** The registry's ingest bot reads those two keys out of the
bundle it has already attested and writes a per-language name and summary into
the signed catalogue — beside the English ones, never instead of them. Nothing
is uploaded and nothing is typed into a form: the text ships inside your bundle,
and a language a release stops shipping leaves the card rather than outliving the
file it came from. A client that has never heard of the per-language member reads
the flat English fields, which is the other reason English is the card.

The card is the one surface a stranger reads *before* installing you, so the
rules follow the text there. The two keys are checked against `plugin.toml`
again, on the downloaded bundle. A translated name is held against every other
listing's names in every language, the way an English one always has been. And a
translation of English you have since rewritten is published as the English,
because a confidently wrong sentence in a language nobody at the registry can
read is worse than a correct one in the wrong language. Everything on that list
that is a fact about your own tree, `astra-plugin locale check` tells you before
a tag exists. The comparison against every *other* listing is not one of them:
only the registry holds the other listings, so that one is met at ingest and
nowhere earlier.

`plugin.toml` itself may **not** carry a `$key` in `name` or `description`.
Those bytes go into `MANIFEST.json` and are read unresolved by the registry, so
a key there is the literal text a user reads on the store card of every Astra
that has ever existed.

**And that is the sentence to read twice, because it decides something these two
keys do not.** `listing.name` localises your **catalogue entry** — the row a
stranger reads in the store. It is not a rename. Your plugin's display name
*inside* Astra starts from `plugin.toml`'s flat `name`, which is English by
construction, and every surface that has no localised source for it shows
exactly that.

Which surfaces inside Astra do show a translated name is the daemon's decision
and it varies between releases — settings pages, provider lists and chat titles
are drawn by different code, and not all of it has ever asked for a language.
**Do not write documentation, release notes or a store description that promises
your users a translated plugin name everywhere.** Promise them what you control:
the store card, your config form, your `[ui]` labels, and every string your own
process produces. Those are the two planes above, and they are yours.

If a translated name matters to you on a particular Astra screen, that is a
feature request against Astra, not something `locales/` can deliver.

### One string you should not key, and it is not a rule

A tool's `description` is an **instruction to a model**, not text a person reads.
Write it in English and leave it alone.

The reason is that the costs are not symmetric. A translation the author never
tested changes which tool the model picks — and when it goes wrong it goes wrong
on a user's machine, in a language the author cannot read, in a report the author
cannot reproduce. An English description on a screen is an inconvenience. One of
those is a correctness bug and the other is cosmetic, and that decides it without
needing anybody's taste.

**This is advice and it is labelled as advice, because nothing enforces it.**
Tools are declared over gRPC at run time, not in `plugin.toml`, so
`astra-plugin check` never sees a tool description and cannot warn you. A rule
written in the tone of a rule, that no tool checks, is worse than a paragraph
that admits what it is.

**It does not contradict what the daemon does, and the difference is worth being
precise about**, because at first glance it looks like it should. Astra resolves
a `$key` wherever one is legal and present — including on fields that reach a
model, such as an action type's `ai_description`. That is correct, and it answers
a different question: *given* a key is there, resolving it is strictly better
than shipping the literal `$action.foo.ai_description` into the prompt.

So the two live at different layers and both hold:

| | says |
|---|---|
| the daemon, on serve | a `$key` that is present gets resolved — always |
| this page, to you | do not put one in a string that instructs a model |

The daemon cannot make this call for you. It sees a key and must render it; only
you know whether the string was a sentence for a person or an instruction for a
model.

### Exactly which strings the daemon resolves, and from which daemon

The declared plane grew on 2026-08-23. This is the current list, and the second
column is the part to read before you rely on any of it.

| Surface | Resolved? |
|---|---|
| config-field titles, descriptions, placeholders, option labels | yes, and always has been |
| `[ui]` contribution labels | yes |
| action and trigger type labels, and their `ai_description` | yes |
| **a TTS or STT plugin's own config fields** — labels, placeholders, descriptions, options | **yes, new** |
| **a tool's `description`** | **yes, new** |
| **a parameter's `description` inside `parameters_json`** | **yes, new** |
| a parameter's NAME — the object key in `parameters_json` | **never.** The model must emit it verbatim |
| a tool's `name` | **never.** It is the dispatch identifier, namespaced and matched back on call |
| `[plugin] name` and `description` | **never**, and a `$key` there is refused at pack time (E20) |

**The three marked new shipped in Astra `v0.2.1`** (2026-09-02), with daemon
commit `aa6fe5f7`. They are false for every daemon older than that, so a plugin
relying on them shows a user its own raw `$key` on anything earlier. That is
what `min_astra_version = "0.2.1"` is for: it makes an older daemon refuse the
install rather than render the key, and `astra-plugin new` writes it into any
scaffold whose labels are keys.

The TTS/STT row has a property the others do not, and it is worth knowing: those
fields are resolved **when the page asks for them**, not when your plugin
registers. So a user changing Astra's language sees your labels change without
restarting anything.

### `default` and `enum` — the one that fails quietly

Inside `parameters_json`, `enum` values and `default` are resolved too, and that
is where to be careful. A key that hits is replaced with your text, as you would
want. **A `$`-prefixed, dotted, key-shaped string that MISSES loses its `$` and
is passed on without it.**

So `"$USD"` and `"$HOME/notes"` are safe — a key needs a dot and a letter-first
first segment, and neither qualifies. `"$config.default_path"` as a *literal
default value* is not safe: if no locale defines it, the model receives
`config.default_path`, and nothing anywhere reports that this happened.

**Do not put a `$key` in `default` or `enum`.** Not because it breaks — it does
not, unless the string is a dotted identifier — but because the case that does
break is silent, and `astra-plugin check` cannot see a tool schema at all: tools
are declared over gRPC at run time, not in `plugin.toml`.

---

## 2 · `$` marks a key. `$$` marks a dollar.

A string that begins with `$` is a **reference**: the daemon looks the rest of
it up in your `locales/`, and puts the translation in its place.

<!-- doctest: toml-manifest locales=1 -->
```toml
[plugin]
id = "chess"
name = "Chess"
version = "0.1.0"
description = "Play chess against a local bot or an Astra model"
author = "You"
license = "MIT"

[entry]
command = "target/release/chess"

[capabilities]
actions = true

[config]
schema = """
{
  "type": "object",
  "properties": {
    "engine_path": {
      "type": "string",
      "title": "$config.engine_path.title",
      "description": "$config.engine_path.description"
    }
  }
}
"""
```

**A key that matches nothing is shown to the user as it is.** Not blanked, not
replaced with English, not logged where you would see it — put on screen, in a
label position, where it reads like a deliberate identifier rather than a
mistake. So the one rule to carry away from this page is that **every key you
reference must exist in `locales/en.json`**, and `astra-plugin check` is the
thing that tells you when one does not:

<!-- doctest: output from="astra-plugin check ., in a project whose schema references a key no locale file defines" unrun="needs a plugin project on disk; reproduce it by deleting one key from locales/en.json in your own plugin and running `astra-plugin check`" -->
```
  ERROR: [E7] [config] schema properties.engine_path.title references `$config.engine_path.title`, which is in no locale file.
        The daemon looks that key up and, finding nothing, renders the BARE KEY —
        the user reads `config.engine_path.title` on the settings form, which looks like a deliberate
        identifier rather than a mistake.
        Fix: add "config.engine_path.title" to locales/en.json, or write the English text here directly.
```

If your text genuinely begins with a dollar — `$5 off`, a `"default"` of
`$HOME/notes` — write **`$$`**. `$$5 off` is data, never a key, and the CLI
will not report it as a missing one.

Exactly which strings a given Astra release resolves, and exactly what it does
with a miss, has changed once and will change again. Do not infer either from
this page: `astra-plugin check` refuses the cases that are unsafe on the daemons
your users actually have, `astra-plugin locale render` shows you what a schema
resolves to without a daemon at all, and the scaffold pairs every `$key` it
emits with the `min_astra_version` that makes it resolve.

---

## 3 · English is mandatory

Every other language falls back to English, so English is not one translation
among ten — it is the base the other nine are defined against. Concretely:

- `locales/` may not exist **without** `locales/en.json`;
- every key family in another locale must be in `en.json`, and the reverse;
- `plugin.description` must be written in the Latin script;
- `en.json` must carry both `listing.*` keys, and they must agree with
  `plugin.toml`.

**Where the gate fires**, in the order you will meet it:

| | |
|---|---|
| `astra-plugin check` | errors fail, notes do not |
| `astra-plugin dev` | refuses to sideload at all unless `check --strict` passes, so a note is free and anything above one stops you |
| `astra-plugin build` | **refuses to pack.** Nothing is written |
| the release workflow | runs `check --strict` before it builds anything, in your repository, on your tag — with the CLI that workflow pins, which is not necessarily the newest one |
| the registry, at ingest | its own rule set, on the bundle it downloaded — because a bundle can reach the catalogue without ever having met this CLI. **Neither list contains the other.** What is a fact about your source tree is settled above, where you can still act on it; what is a fact about the *catalogue* — how your name in each language sits beside every other listing's — can only be settled here, and the registry states its own rules in its own repository. This gate refuses a listing *after* a tag is pushed, which is the expensive place to learn any of it |

The English check is a **script check, not a language detector**. It refuses a
description written entirely in another alphabet — which is the accident it
exists to catch, and the one that has actually happened. It cannot tell English
from French, and a card written in fluent French passes every gate here.

Every finding carries an id — `[E7]` above, `[N3]` in §6. This page deliberately
does not table them: the rules move with the CLI and a copy here would move with
nothing. `astra-plugin locale check` prints each one in full with its fix, and
`astra-plugin locale check --json` prints the same thing machine-readably.

---

## 4 · Adding a language

<!-- doctest: cli -->
```bash
astra-plugin locale ls
astra-plugin locale add ru
astra-plugin locale sync
astra-plugin locale check
astra-plugin locale extract
astra-plugin locale render --lang ru
astra-plugin locale pseudo
```

<!-- doctest: output from="astra-plugin locale --help" -->
```
Manage `locales/` — the plugin's translations, and its store card's text.

A plugin ships one flat `locales/<code>.json` per language beside `plugin.toml`. `astra-plugin check` and `astra-plugin build` enforce the rules over that directory; these commands are how you satisfy them without reading them.

Usage: astra-plugin locale [OPTIONS] <COMMAND>

Commands:
  ls       The vocabulary, what this plugin ships, key counts and deltas
  add      Seed a locale from `en.json`, with the plural rows that code needs
  sync     Rewrite `locales.lock.json`, and `en.json`'s two `listing.*` keys
  check    The locale rules alone, without the rest of `astra-plugin check`
  extract  Which `$keys` in `plugin.toml` are absent from `locales/en.json`
  render   Walk `[config] schema` locally and print every string, marking which are `$` references and which are hardcoded literals
  pseudo   Write `locales/qps.json` — every English string, bracketed and padded
  help     Print this message or the help of the given subcommand(s)

Options:
      --json
          Print one JSON document instead of human output. Progress lines are suppressed so the output is safe to pipe

      --path <PATH>
          Path to plugin directory (default: current directory)

          [default: .]

  -h, --help
          Print help (see a summary with '-h')
```

The whole loop is four commands:

**1. Write the English.** Every user-visible string goes in `en.json`, keyed
however you like. `astra-plugin locale extract` lists the `$keys` your manifest
references and `en.json` does not define yet, in a form you can paste.

**2. Seed the language.**

<!-- doctest: output from="astra-plugin locale add ru" unrun="writes locales/ru.json into a plugin project; re-run it in your own plugin" -->
```
Created locales/ru.json — 8 key(s) seeded from locales/en.json, values still English.
  Added the plural rows ru needs: msg.done.few, msg.done.many.
  locales.lock.json: 0 fresh, 0 newly translated, 8 untranslated, 0 stale.
Translate the values in place; leave the keys alone. Then `astra-plugin locale sync`.
```

The file starts as a copy of the English one, so nothing is missing and nothing
is broken while you work. **Translate the values in place and leave the keys
alone** — a key you invent in `ru.json` alone is an error, in both directions,
because a language whose key set differs from English's is a language in which
some label has nothing to fall back to.

`add` never overwrites a translated value, and it names every key it removes
rather than removing it quietly. If `en.json` can no longer seed a key — because
the key was renamed or dropped — and a translation of the old name is still
present, `add` **refuses** instead of guessing: it cannot tell a rename from a
deletion, and a translation is the one thing in `locales/` that cannot be
regenerated. `--prune` is how you say "delete them, I meant it". Reach for it
only after reading the names it printed.

`add` refuses a code Astra cannot be set to. `zh-CN` is the one people reach for
and it is not a thing here: Chinese is `zh`, there are no region tags anywhere,
and a `locales/zh-CN.json` would be packed, digested, signed, installed, and
read by nothing. The ten codes are in
[`spec/locales.yaml`](../../../spec/locales.yaml).

**3. Translate, then `sync`.**

<!-- doctest: output from="astra-plugin locale sync" unrun="rewrites locales.lock.json in a plugin project; re-run it in your own plugin" -->
```
locales.lock.json: 8 fresh, 0 newly translated, 0 untranslated, 0 stale.
```

**4. Check.**

<!-- doctest: output from="astra-plugin locale ls" unrun="reads a plugin project's locales/; re-run it in your own plugin" -->
```
spec/locales.yaml declares 10 codes; this plugin ships 2.
  en        6 key(s),   5 families   missing 0, extra 0, stale 0
  ru        8 key(s),   5 families   missing 0, extra 0, stale 0
  not translated: uk de fr es pt ja zh ko
```

The first line is printed before anything else and unconditionally, so a plugin
with no locale files at all reads as *empty* rather than as *fine*.

---

## 5 · Plurals

Russian needs four forms of a counted noun and Japanese needs one, so a plural
is a **family of keys** rather than one key with a rule attached:

<!-- doctest: json -->
```json
{
  "msg.done.one": "Сыгран {n} ход",
  "msg.done.few": "Сыграно {n} хода",
  "msg.done.many": "Сыграно {n} ходов",
  "msg.done.other": "Сыграно {n} хода"
}
```

`locale add` writes exactly the rows that language needs, and `check` holds you
to exactly those — too few or too many is an error, in both directions, per
language. The categories, and which language takes which, are declared once in
[`spec/i18n.yaml`](../../../spec/i18n.yaml) and generated into all three SDKs
from there.

Key **families**, not raw keys, are what parity is measured over. `en.json`
carries `msg.done.one` and `msg.done.other`; `ru.json` carries four rows;
neither is missing anything, because both declare the family `msg.done`.

Resolve one with `tn`, which picks the row and substitutes the count:

<!-- doctest: rust-plugin -->
```rust
use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct Chess;

#[astra::plugin]
impl Chess {
    /// A literal English label — still a valid choice, and the one that needs
    /// no `min_astra_version`. Astra 0.2.1 resolves `$keys` on this surface, so
    /// a key would work too, at the cost of refusing every older daemon. §2 is
    /// the table of what is resolved where.
    #[action(label = "Play a move")]
    async fn play(&self, ctx: &PluginContext) -> Result<String, ActionError> {
        let moves: i64 = 3;
        // RUNTIME plane: resolved here, now, with a count the daemon cannot know.
        Ok(ctx.i18n().tn("msg.done", moves, &[("n", &moves.to_string())]))
    }
}

astra::main!(Chess::default());
```

`ctx.i18n()` is the short path and the one to reach for: it loads `locales/` on
first use and follows the context's language from then on, so a handler never
has to remember `set_language` and `OnLanguageChanged` is not something your
plugin has to implement to be correct.

Where it looks is `$ASTRA_PLUGIN_DIR/locales`, then `./locales`, and nowhere it
does not own — a TypeScript plugin runs as `node dist/index.js` and a Python one
as `python -m src.plugin`, so an executable-relative search would have them
reading `/usr/bin/locales`. Loading never fails, which is the right behaviour
for a loader and the wrong one for a mistyped filename, so every file it could
not use is on `load_errors()` and `astra-plugin test` turns each one into a
failed probe rather than leaving it to be discovered by a user.

If your own logic depends on how many keys you shipped — one of *n* greetings,
say — ask `count_prefixed` rather than writing the number down. It counts across
the union of every locale you ship, so a language you have not finished
translating cannot change it.

---

## 6 · Staleness, and `locales.lock.json`

When you change an English sentence, every translation of it becomes a
confidently wrong sentence that nothing will ever correct. The lock is what
notices.

<!-- doctest: json -->
```json
{
  "schema": "astra.plugin.locales/1",
  "source": "en",
  "locales": {
    "ru": {
      "listing.name": "9f2a1c4e77b1",
      "config.engine_path.title": "b70e2f19c034"
    }
  }
}
```

Each value is a short digest of the **English bytes that value was made
against** — of the English, not of the translation, and of the bytes as they
stand, unnormalised. The exact form is the CLI's and the registry's to agree on
and is not something to reproduce by hand: nothing here is asserted, `sync`
derives the whole file, and `astra-plugin locale check` is what reads it back.

**Every key gets an entry, including one whose value is still English.** A seed
is a copy of a sentence, and a copy is exactly the thing a later edit has to be
able to invalidate. When a key's digest no longer matches today's English it is
**stale** — `[N3]` if somebody translated it, `[N15]` if the value is still the
English it was seeded from and `en.json` has moved on since.

Leaving the seeds unrecorded is how this went wrong once, and the failure is
worth knowing because none of it was visible from here. A value equal to English
got no entry, so the first `sync` after an English edit saw *differs from
English, no entry*, read that as a fresh translation, and stamped it with the
digest of the **new** English. Nothing could report it stale afterwards on
either side of the release — and the registry, which reads this same number,
published the plugin's previous English text as its Russian and Japanese store
card.

A plural row a language needs and English cannot carry — `ru`'s `few` and
`many`, which `en.json` may not contain — is measured against `<base>.other`. So
rewriting the English ages the whole family, rather than the two rows English
happens to share names with.

<!-- doctest: output from="astra-plugin locale check, after editing one English value" unrun="needs a plugin project whose en.json has changed since the last sync; reproduce it by editing one value in your own en.json" -->
```
  NOTE: [N3] locales/ru.json: 1 stale translation(s) (config.engine_path.description).
        The English these were translated from has changed since. A published bundle may
        not ship a translation that describes older English — a reader gets a sentence
        that is confidently wrong and nothing ever corrects it.
        Fix: retranslate and run `astra-plugin locale sync`, or accept them as still
             correct with `astra-plugin locale sync --accept ru`.
```

A note while you work; an **error** at `astra-plugin build`, because the
artifact is the thing a stranger reads. `--accept ru` clears it and prints what
it accepted, so the decision lands in a diff somebody can review. It is a rubber
stamp by construction — the mechanism knows the English *changed*, never that the
translation is *wrong* — which is exactly why it leaves a trace.

`[N15]` is a note at **both** gates and `build` does not refuse it, because the
harm is a different size: a stale translation puts a confidently wrong sentence
in front of a reader in their own language, while a seed the English moved out
from under puts English in front of a reader who was always going to get English.
Out-of-date English, which is worth saying and is not worth refusing a release
over a file nobody claimed to have translated.

The lock lives at the plugin root and not inside `locales/`, because everything
in `locales/` that ends in `.json` is a locale: a `locales/locales.lock.json`
would become a language called `locales.lock`.

---

## 7 · Four things that surprise people

**Once your plugin ships a `locales/` directory, do not rely on the order of
your config properties.** Resolving a schema means parsing it and re-serialising
it, the map that happens through is sorted by key, and the settings form renders
fields in the order the JSON hands them over — so the fields come out in
**alphabetical order of their property names** rather than the order you wrote
them in. There is no ordering member you can add to say otherwise: nothing reads
one. The property names are the only lever, and `astra-plugin locale render
--lang <code>` shows you the result without a daemon.

(Exactly *which* schemas take that round trip has already changed once — the
condition is a detail of the daemon you are running, and the safe assumption is
the one above.)

**A permission `reason` is never translated.** Its exact bytes are inside the
hash three implementations compute and the registry countersigns, and it is
shown on the consent sheet *before* your plugin is installed. Write it in
English, and keep it short — the cap is in
[`spec/listing-limits.yaml`](../../../spec/listing-limits.yaml), which also says
which unit it counts in, and
`astra-plugin check` refuses a manifest over it rather than letting the registry
do it after your tag. The permission **label** beside it is Astra's string, not
yours: Astra shows it in the languages whose own UI translation it holds
complete — `maintained` in [`spec/locales.yaml`](../../../spec/locales.yaml),
which is a smaller set than the ten you may ship a locale file for — and falls
back to English, per key, in the others.

**A TypeScript plugin must not `import` its locale files.** Only the `locales/`
directory beside `plugin.toml` is packed, and the daemon reads it off disk.
`import en from "./locales/en.json"` is the trap: esbuild inlines the JSON into
`dist/`, so your own runtime strings work perfectly while the settings form fills
with raw keys — and it is worse still if the file the import names lives
somewhere the packer never looks. One source, on disk, beside `plugin.toml`, in
all three languages; read it with `I18n.discover()`. `check` NOTEs that import
when it sees it.

**`locale pseudo` cannot reach the declared plane.** It writes `locales/qps.json`
so that anything still in plain English at run time is a string you never
externalised — but `qps` is not a language Astra can be set to, so the daemon can
never be asked for a `qps` config schema. That half is `locale render`'s job.
`build` refuses a bundle carrying `qps.json`.

---

## See also

- [Config and settings fields](config-fields.md) — where the declared plane
  actually renders
- [`spec/locales.yaml`](../../../spec/locales.yaml) — the ten codes, and how the
  list is changed
- [`spec/i18n.yaml`](../../../spec/i18n.yaml) — the fallback chain, the
  placeholder grammar, the plural table
- [Rust SDK](../4-sdk/rust.md) · [Python SDK](../4-sdk/python.md) ·
  [TypeScript SDK](../4-sdk/typescript.md) — `I18n` in each
- [`examples/telegram-client`](../../../examples/telegram-client) — a config
  schema of `$keys` with `en`/`ru` beside it;
  [`examples/companion`](../../../examples/companion) — the runtime plane, and a
  count taken from the locale files rather than written down

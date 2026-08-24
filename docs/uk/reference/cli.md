> Переклад. Джерело істини — [docs/en](../../en/reference/cli.md); за розбіжності відповідає англійська версія. Англійська сторінка згенерована `tools/docgen/cli.py`; ця перекладна копія не генерується автоматично і може відстати при зміні джерела.

# Довідник CLI

`astra-plugin 0.3.0`. Кожен прапорець нижче прочитаний з бінарника, тож ця
сторінка не може описувати опцію, якої не існує. Джерело —
[`astra-plugin-cli/src/main.rs`](../../../astra-plugin-cli/src/main.rs).

Astra Plugin Development CLI

## Всюди

| Опція | Опис |
|---|---|
| `--json` | Print one JSON document instead of human output. Progress lines are suppressed so the output is safe to pipe |
| `-h, --help` | Print help |
| `-V, --version` | Print version |

## Команди

| Команда | Псевдоніми | Що робить |
|---|---|---|
| [`new`](#astra-plugin-new) | `create` | Create a new plugin project from a template |
| [`dev`](#astra-plugin-dev) | — | Start a plugin in dev mode (sideload into the running Astra + hot-reload) |
| [`build`](#astra-plugin-build) | — | Build a plugin into a distributable .astraplugin bundle |
| [`sign`](#astra-plugin-sign) | — | Append the retiring in-ZIP SIGNATURE/PUBKEY pair to a built bundle |
| [`verify`](#astra-plugin-verify) | — | Verify a built .astraplugin bundle and print its digests |
| [`test`](#astra-plugin-test) | — | Run the conformance suite against a real plugin process |
| [`doctor`](#astra-plugin-doctor) | — | Answer, in one command, every question asked when a plugin will not start: toolchains, the daemon, the manifest, the entry point, permissions, the platform block, the release workflow |
| [`logs`](#astra-plugin-logs) | — | Read a plugin's output from the daemon that spawned it |
| [`check`](#astra-plugin-check) | `validate` | Check a plugin manifest, config schema and release workflow |
| [`init-ci`](#astra-plugin-init-ci) | — | Write .github/workflows/release.yml, pinned to a commit of the Astra reusable workflow. Re-run it to upgrade the pin; it keeps your inputs |
| [`version`](#astra-plugin-version) | — | Set the version in plugin.toml and every other manifest at once |
| [`publish`](#astra-plugin-publish) | — | Get a release listed: preflight it, or open a prefilled submission |
| [`keygen`](#astra-plugin-keygen) | — | Generate the OPTIONAL Ed25519 keypair `astra-plugin sign` uses |

### Команди `astra-plugin login` не існує

**`login`** тут **немає**. Потрапляння плагіна до каталогу йде через
браузер, у якому автор уже увійшов до облікового запису, — реєстр читає
засвідчені бандли з релізу GitHub і верифікує кожен з нуля, тож заявка
несе репозиторій і тег, і нічого більше. Це означає: не треба створювати
другий обліковий запис, нічого інтегрувати з keyring'ом, немає файлу
облікових даних, який можна злити, і немає токена в історії оболонки.
`login` тут був би сховищем облікових даних, побудованим заради того, про
що ніхто не просить.

## astra-plugin new

Також пишеться як `astra-plugin create`.

Create a new plugin project from a template

```
Usage: astra-plugin new [OPTIONS] <NAME>
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `<NAME>` | Plugin name (lowercase, hyphens allowed) |

**Опції**

| Опція | Опис |
|---|---|
| `-l, --lang <LANG>` | Programming language (default `rust`) |
| `-t, --template <TEMPLATE>` | What kind of plugin this is. Picks the capabilities and the example code; `--capabilities` overrides the capability set it implies (default `tool`; one of `tool`, `tts`, `stt`, `stt-streaming`, `ai-provider`, `ui`, `action-trigger`, `client`, `blank`) |
| `-c, --capabilities <CAPABILITIES>` | Capabilities (comma-separated: tools, tts, stt, ai_provider, client, actions, triggers, ui_contributions, event_handlers, dom_access). Overrides whatever --template implies |
| `-o, --output <OUTPUT>` | Output directory (default: ./<name>) |

## astra-plugin dev

Start a plugin in dev mode (sideload into the running Astra + hot-reload)

```
Usage: astra-plugin dev [OPTIONS] [PATH]
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `[PATH]` | Path to plugin directory (default: current directory) (default `.`) |

**Опції**

| Опція | Опис |
|---|---|
| `--daemon-addr <DAEMON_ADDR>` | Daemon gRPC address. Defaults to the port the running daemon wrote to <config>/daemon.port, else 127.0.0.1:32000 |
| `--standalone` | Spawn the plugin process directly instead of asking the daemon to. The plugin cannot register with Astra this way — see the note it prints |

## astra-plugin build

Build a plugin into a distributable .astraplugin bundle

```
Usage: astra-plugin build [OPTIONS] [PATH]
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `[PATH]` | Path to plugin directory (default: current directory) (default `.`) |

**Опції**

| Опція | Опис |
|---|---|
| `-o, --output <OUTPUT>` | Output file path. Defaults to <id>-<version>-<target>.astraplugin, which is the name a published bundle must have — the target segment is the registry's platform key |
| `--target <TARGET>` | Platform this bundle is for: linux-x64, windows-x64, or noarch. Defaults to the host for native plugins and noarch for TypeScript/Python |
| `--reproducible` | Assert deterministic packing: sorted entries, mtime 1980-01-01, fixed compression level. Two builds from the same inputs produce the same sha256 |
| `--all-targets` | Build every bundle this plugin needs to be installable everywhere Astra runs. One file for TypeScript and Python (noarch); one per platform for Rust, each from its own `cargo build --target` |

**Приховано: `--no-sign`.** Приймається, і відсутнє в `--help`
(`#[arg(hide = true)]`). Застарілий no-op: `build` ніколи не підписує.
Збережено, тому що закріплений workflow релізу його передає, а видалення
прапорця зламало б кожен уже опублікований workflow автора. Видаляється
разом з парою формату, що йде на спокій.

## astra-plugin sign

Append the retiring in-ZIP SIGNATURE/PUBKEY pair to a built bundle.

An optional second factor, not a trust signal: Astra checks the in-ZIP pair against a pinned Astra publisher key, so a bundle signed with your own key is untrusted exactly as an unsigned one is. What makes Astra install a plugin is the registry record countersigning sha256(whole file). Both this command and the format entries it writes are removed in a future release.

```
Usage: astra-plugin sign [OPTIONS] <FILE>
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `<FILE>` | The .astraplugin to sign, in place |

**Опції**

| Опція | Опис |
|---|---|
| `--key <KEY>` | Read the Ed25519 seed from this path instead of ~/.astra/plugin-keys/private.key. A path, never the key itself |

## astra-plugin verify

Verify a built .astraplugin bundle and print its digests

```
Usage: astra-plugin verify [OPTIONS] <FILE>
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `<FILE>` | Path to the .astraplugin file |

## astra-plugin test

Run the conformance suite against a real plugin process.

Starts the plugin the way the daemon starts it, against a mock daemon serving PluginHostService, and calls every inbound hook that the manifest's capabilities imply. A hook `spec/hooks.yaml` marks `required` may not answer UNIMPLEMENTED; an `optional` one may, because UNIMPLEMENTED is the protocol's way of saying "this hook is absent".

```
Usage: astra-plugin test [OPTIONS] [PATH]
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `[PATH]` | Path to plugin directory (default: current directory) (default `.`) |

**Опції**

| Опція | Опис |
|---|---|
| `--no-build` | Use whatever is already built instead of building first |
| `--report <REPORT>` | Write the machine-readable conformance report here |

## astra-plugin doctor

Answer, in one command, every question asked when a plugin will not start: toolchains, the daemon, the manifest, the entry point, permissions, the platform block, the release workflow

```
Usage: astra-plugin doctor [OPTIONS] [PATH]
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `[PATH]` | Path to plugin directory (default: current directory). Project checks are skipped when it holds no plugin.toml (default `.`) |

**Опції**

| Опція | Опис |
|---|---|
| `--daemon-addr <DAEMON_ADDR>` | Daemon gRPC address to probe |

## astra-plugin logs

Read a plugin's output from the daemon that spawned it

```
Usage: astra-plugin logs [OPTIONS] [PLUGIN_ID]
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `[PLUGIN_ID]` | Plugin id. Default: the plugin.id of the manifest in --path |

**Опції**

| Опція | Опис |
|---|---|
| `--path <PATH>` | Where to look for a plugin.toml when no id is given (default `.`) |
| `--daemon-addr <DAEMON_ADDR>` | Daemon gRPC address |
| `-n, --lines <LINES>` | How many lines of tail to ask for (default `200`) |
| `-f, --follow` | Keep polling until Ctrl+C |

## astra-plugin check

Також пишеться як `astra-plugin validate`.

Check a plugin manifest, config schema and release workflow

```
Usage: astra-plugin check [OPTIONS] [PATH]
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `[PATH]` | Path to plugin directory (default: current directory) (default `.`) |

**Опції**

| Опція | Опис |
|---|---|
| `--strict` | Treat warnings as errors |
| `--fix` | Apply the fixes that can be applied mechanically, then re-check. Only rewrites what it can prove; everything else is still reported |
| `--resolve-pin` | Ask GitHub whether the release workflow pin is current. Off by default: `astra-plugin dev` runs `check --strict` on every start, and the release workflow tells the check what it is running from through ASTRA_PLUGIN_WORKFLOW_SHA, so neither needs the network |

## astra-plugin init-ci

Write .github/workflows/release.yml, pinned to a commit of the Astra reusable workflow. Re-run it to upgrade the pin; it keeps your inputs

```
Usage: astra-plugin init-ci [OPTIONS] [PATH]
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `[PATH]` | Path to plugin directory (default: current directory) (default `.`) |

**Опції**

| Опція | Опис |
|---|---|
| `--ref <WORKFLOW_REF>` | A 40-hex commit to pin (used verbatim, no network), or a ref name to resolve. Default: the released workflow tag, else the default branch head |
| `--linux-packages <LINUX_PACKAGES>` | Set the linux-packages input, e.g. "libasound2-dev pkg-config". Omitted, an existing file's value is kept |
| `--offline` | Never touch the network: keep the pin already in the file |

## astra-plugin version

Set the version in plugin.toml and every other manifest at once

```
Usage: astra-plugin version [OPTIONS] <VERSION> [PATH]
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `<VERSION>` | The new version, strict semver and without a leading 'v' |
| `[PATH]` | Path to plugin directory (default: current directory) (default `.`) |

**Опції**

| Опція | Опис |
|---|---|
| `--allow-downgrade` | Allow a version that sorts below the current one. Astra refuses to install a downgrade, so such a release is uninstallable |

## astra-plugin publish

Get a release listed: preflight it, or open a prefilled submission.

Uploads nothing and holds no credential — the registry reads the attested bundles off your GitHub Release and verifies every one of them from scratch, so a submission carries only your repository and a tag.

```
Usage: astra-plugin publish [OPTIONS] [PATH]
```

**Аргументи**

| Аргумент | Опис |
|---|---|
| `[PATH]` | Path to plugin directory (default: current directory) (default `.`) |

**Опції**

| Опція | Опис |
|---|---|
| `--dry-run` | Run every check the registry runs that can be run locally, name the ones only the registry can run, and stop |
| `--notify` | A release ping for a plugin that is ALREADY listed — task 3.4's manual escape hatch, for when the registry has not noticed a release by itself. Without it, this opens a first listing request |
| `--repo <REPO>` | Source repository as `owner/name`. Default: the `origin` remote |
| `--tag <TAG>` | Release tag. Default: the plugin's tag prefix plus its version |
| `--print-url` | Print the URL and do not open a browser |

## astra-plugin keygen

Generate the OPTIONAL Ed25519 keypair `astra-plugin sign` uses.

You do not need one to publish: `build` does not read it, and Astra's trust comes from the registry record over sha256(whole file), not from any key you hold.

```
Usage: astra-plugin keygen [OPTIONS]
```

**Опції**

| Опція | Опис |
|---|---|
| `--force` | Overwrite existing keypair |

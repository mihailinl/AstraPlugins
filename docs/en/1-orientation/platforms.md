# Platforms

Astra ships a daemon for **two** hosts. Everything below follows from that.

| Platform key | Host | Astra ships a daemon |
|---|---|---|
| `linux-x64` | Linux, x86_64 | yes |
| `windows-x64` | Windows, x86_64 | yes |
| `noarch` | any — an interpreted plugin with no native code | n/a, it runs on both |
| `linux-arm64` · `windows-arm64` · `macos-x64` · `macos-arm64` | — | **no** |

The last row is *reserved, not supported*. The names exist in the registry
schema so the index format never has to change if Astra later ships those hosts,
and so a validator can reject a typo (`mac-amd64`) instead of writing a key no
daemon will ever look up. A bundle published under one of them has no host to
run on. `astra-plugin build` refuses to guess: on a host it has no key for it
tells you to pass `--target` explicitly rather than silently packing something
that resolves to `linux-x64`.

## One bundle per platform, and what decides how many you need

<!-- doctest: cli -->
```bash
astra-plugin build --target linux-x64
astra-plugin build --target windows-x64
astra-plugin build --all-targets
```

- **Rust** compiles to native code, so it needs one bundle per platform. The
  release workflow builds them on a matrix — `ubuntu-24.04` and
  `windows-2022` — because a cross-build is a different set of bugs.
- **TypeScript and Python** produce a single `noarch` bundle. The index writes
  the same URL and digest under every supported platform key, so a `noarch`
  bundle is found under `linux-x64` and `windows-x64` like any other.

`--all-targets` builds everything the plugin needs to be installable everywhere
Astra runs: one file for TypeScript and Python, one per platform for Rust, each
from its own `cargo build --target`.

## `[platform]`, and why an omitted block is a claim

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "native-thing"
name = "Native Thing"
version = "0.1.0"
license = "MIT"
author = "You"

[entry]
command = "bin/native_thing"

[capabilities]
tools = true

[platform]
os = ["linux", "windows"]
arch = ["x86_64"]
```

An empty or absent `[platform]` means *no requirement*, and the daemon considers
the plugin compatible everywhere. That is correct for a `noarch` plugin and
wrong for one shipping a native binary. `astra-plugin doctor` says so in exactly
those terms:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Will this install on the platforms I expect?
         no [platform] block, so the daemon considers it compatible everywhere. Correct for a
         noarch plugin; wrong for one that ships a native binary.
```

`astra-plugin build` stamps the real answer into the bundle's `MANIFEST` from
`--target`, so the packaged file carries `{os, arch}` whatever the manifest
says.

## Build prerequisites

| Language | Needs | Checked by |
|---|---|---|
| Rust | Rust **1.85 or newer** — the SDK and the scaffold are edition 2024 | `astra-plugin doctor` |
| Rust | **`protoc` on PATH.** `astra-plugin-sdk/build.rs` compiles `proto/plugin.proto` with `tonic_build::configure().compile_protos(…)`, and tonic-build 0.12 shells out to `protoc` rather than shipping one. `apt install protobuf-compiler` / `pacman -S protobuf` / `brew install protobuf` / `winget install Google.Protobuf` | `astra-plugin doctor` |
| TypeScript | Node 20+ to run, and `bun` (or the `build` script's bundler) to bundle | `astra-plugin doctor` |
| Python | `python3`, plus `grpcio` and `protobuf` from `requirements.txt` | `astra-plugin doctor` |

`protoc` is the one that bites first and reads as something else. The CLI
depends on the Rust SDK, so it is needed to *install `astra-plugin` itself* —
before you have a project, a manifest, or any reason to suspect a protobuf
compiler. Without it `cargo install` stops at
`error: failed to run custom build command for astra-plugin-sdk`, with
`Could not find `protoc`` some lines further down. This repository's own CI
installs it in every Rust job (`arduino/setup-protoc@v3`, seven times in
`.github/workflows/ci.yml`), which is the clearest evidence that it is not
optional.

`astra-plugin doctor` answers all of this in one command, on the machine you are
actually on:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [ok  ] Can I build a Rust plugin?
         cargo 1.97.0 (c980f4866 2026-06-30)
  [ok  ] Can I compile the SDK's protobufs?
         libprotoc 35.1
  [ok  ] Can I build and run a TypeScript plugin?
         node v26.4.0
  [ok  ] What will bundle my TypeScript?
         bun — `astra-plugin build` uses bun run build
  [ok  ] Can I build and run a Python plugin?
         python3: Python 3.14.6
```

### The glibc floor

A Linux bundle built in CI is checked against **GLIBC_2.39** — the release
workflow disassembles every ELF object in the finished archive and fails the
build if anything needs a newer symbol version. That is what makes a plugin
built on `ubuntu-24.04` run on the distributions Astra targets, and it is the
kind of failure that otherwise only appears on a user's machine.

If you build a Linux bundle by hand on a newer distribution, nothing checks
this. That is one of several reasons the release path is CI.

### TypeScript bundles carry no `node_modules`

A `.astraplugin` ships the bundled output, not a dependency tree. The release
workflow asserts the bundle is self-contained: a stray `require("chalk")` that
the bundler could not follow installs fine and dies at first launch with
`MODULE_NOT_FOUND`, on a machine where nobody can fix it.

## Where things live, per OS

Astra resolves its directories with the `directories` crate, from
`("com", "astra", "astra")` — the CLI uses the identical call so the two cannot
disagree (`astra-plugin-cli/src/daemon.rs`).

| | Linux | Windows |
|---|---|---|
| Config dir | `~/.config/astra` | `%APPDATA%\astra\astra\config` |
| Daemon port file | `<config>/daemon.port` | same |
| Daemon bootstrap secret | `<config>/daemon.token` | same |
| Installed plugins | `<config>/plugins/<id>/` | same |
| A plugin's settings | `<config>/plugins/<id>/config.json` | same |
| Daemon logs | `<config>/logs/` | same |

Ask, rather than assume — `doctor` prints the path this machine resolved:

<!-- doctest: output from="astra-plugin doctor ." unrun="reports this machine's toolchains, daemon and config paths, so its output differs on every machine" -->
```
  [warn] Where does the CLI look for the running daemon?
         /home/you/.config/astra — but there is no daemon.port in it, so the CLI will fall
         back to 127.0.0.1:32000
```

The daemon takes an OS-assigned port when 32000 is busy, so `127.0.0.1:32000` is
a fallback guess and `daemon.port` is the fact.

## macOS

Not supported, and not by omission. Astra's own release workflow builds
`linux-x64` and `windows-x64` only, so a `macos-arm64` plugin bundle would have
no host; macOS would additionally raise Apple notarization for every third-party
author. The key names are reserved in the index schema, nothing emits them, and
an unhandled host is a hard error rather than a silent fallback. Revisit in the
release where Astra ships a daemon for that target.

# Install the CLI

Everything in the publishing path starts with a command, and this is the page
that gets you the command. The binary is called **`astra-plugin`** — not
`astra-plugin-cli`, which is only the crate's name.

## The honest state of this

**There are no prebuilt binaries yet, and `astra-plugin-cli` is not on
crates.io.** Verified today: `https://index.crates.io/as/tr/astra-plugin-cli`
answers `404`, while `astra-plugin-sdk` at the same index answers `200`, so that
is a real absence rather than a lookup that failed. `gh release list --repo
mihailinl/AstraPlugins` prints nothing.

So the only way to get the CLI is to build it, and building it needs a Rust
toolchain. Shipping prebuilt binaries is a known, separate, pending task — the
release automation for it is being written now, and this page will grow a
download line the day a release exists to download. Until then it describes the
whole of what exists, and nothing here asks you to download anything.

That cost is real, and it is worth naming why it is worth paying anyway: the CLI
is not a convenience wrapper around some other, easier route. It is the only
thing that writes a correct release workflow, the only thing that keeps your
manifests from disagreeing about the version, and the only thing that opens a
listing request the registry's bot will actually see. Routing around it is how
two real submissions ended in silence — see
[what publishing is](publishing.md).

## Prerequisites

| | Why | Check |
|---|---|---|
| **Rust 1.85 or newer** | every crate here is `edition = "2024"`, and 1.85 is the first release that understands it | `cargo --version` |
| **`protoc` on `PATH`** | the CLI depends on `astra-plugin-sdk`, whose `build.rs` compiles `proto/plugin.proto` with `tonic-build`, which shells out to an external `protoc` | `protoc --version` |
| **`git`** | `cargo install --git` clones with it | `git --version` |

No crate declares a `rust-version`, and CI builds on `stable`, so the edition is
the only floor actually enforced.

Installing `protoc`, which is the one people miss:

<!-- doctest: illustrative reason="OS package-manager commands; the doc-test runner has one OS and installing system packages during a documentation check is not something a CI job should be allowed to do" -->
```
Debian/Ubuntu   sudo apt install protobuf-compiler
Arch            sudo pacman -S protobuf
Fedora          sudo dnf install protobuf-compiler
macOS           brew install protobuf
Windows         winget install Google.Protobuf     (or scoop install protobuf)
```

Without it the build fails in `astra-plugin-sdk`'s build script, and the error
names the fix:

<!-- doctest: output from="PROTOC=/nonexistent/protoc cargo build --release, run in astra-plugin-sdk/ — there is no workspace manifest at the repository root, so `-p astra-plugin-sdk` from the root cannot work" unrun="a full SDK build pointed at a protoc that does not exist; minutes long, and it has to fail to print this" -->
```
  Error: Custom { kind: NotFound, error: "Could not find `protoc`. If `protoc` is installed, try setting the `PROTOC` environment variable to the path of the `protoc` binary. To install it on Debian, run `apt-get install protobuf-compiler`. It is also available at https://github.com/protocolbuffers/protobuf/releases  For more information: https://docs.rs/prost-build/#sourcing-protoc" }
```

## Install it

**One line, no clone.** This is the one to use:

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

`--locked` builds against the checked-in `Cargo.lock` rather than re-resolving
every dependency to its newest release, which is the difference between a build
that works the same way it worked here and one that finds out about a breaking
patch release on your machine.

`--git` builds whatever `master` currently carries, so the version and the commit
it reports are whatever is on `master` when you run it. Everything in angle
brackets below differs per machine and per run — the version and the SHA come
from `master`, the paths from your home directory, the duration from your CPU:

<!-- doctest: output from="cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --root <scratch> --locked" unrun="clones over the network and compiles for minutes; a documentation check must not do either" -->
```
   Compiling astra-plugin-cli v<version> (<home>/.cargo/git/checkouts/astraplugins-341ed6441d668bfa/<short-sha>/astra-plugin-cli)
    Finished `release` profile [optimized] target(s) in <duration>
  Installing <scratch>/bin/astra-plugin
   Installed package `astra-plugin-cli v<version> (https://github.com/mihailinl/AstraPlugins#<short-sha>)` (executable `astra-plugin`)
warning: be sure to add `<scratch>/bin` to your PATH to be able to run the installed binaries
```

That transcript was produced with `--root <scratch>` so that capturing it did not
overwrite anybody's installed binary. **Leave `--root` off** — as the command
above does — and the last two lines change: `Installing` names
`<home>/.cargo/bin/astra-plugin`, and the `PATH` warning appears only if
`~/.cargo/bin` is not already on your `PATH`. The two SHAs are the same commit
printed at two different lengths, which is cargo's doing, not a mismatch.

**From a clone**, if you want to read or change the CLI as well as run it:

<!-- doctest: cli -->
```bash
git clone https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

A bare `git clone` checks out `master`, and `master` is where the current CLI
is — there is no branch you have to know about.

## Check that it worked

<!-- doctest: cli -->
```bash
astra-plugin --version
astra-plugin --help
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin <version>
```

The number is a placeholder because neither install line lets you choose one:
both build a commit, not a release, so what you get is the version in that
commit's `Cargo.toml`. `0.2.1` is the newest entry in
[the CLI's changelog](../../astra-plugin-cli/CHANGELOG.md), which also records
that this crate has no release train — no crates.io, no tag, no binaries.

If the shell cannot find it, `cargo install` put it in `~/.cargo/bin` (or
`%USERPROFILE%\.cargo\bin` on Windows) and that directory is not on your `PATH`.
`cargo` prints a warning saying exactly that when it happens.

### The bug that breaks a first release, and how to tell whether your build has the fix

**`astra-plugin init-ci` used to pin an annotated tag's *object* SHA where GitHub
requires a commit**, so the first `git push --tags` failed with `invalid value
workflow reference` before any job started. That was
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2).

**The fix is commit `5b8ab22`, not a version number**, and this is the part that
catches people out. There is no release train here — nothing is published, so
nobody installs a chosen version; everybody builds whatever commit they cloned.
`5b8ab22` landed on `master` *before* the bump that raised the number to
`0.2.1`, which means:

- a build made from `master` after `5b8ab22` **has the fix and still prints
  `0.2.0`** — that is not a broken build;
- no `0.2.1` build can *lack* the fix, because `5b8ab22` is an ancestor of the
  bump commit;
- a `0.2.0` build made *before* `5b8ab22` is the broken one, and `--version`
  cannot distinguish it from the first case.

So `0.2.1` is worth having — it is the first number that answers the question by
itself, which is exactly why it exists — but a `0.2.0` that says `0.2.0` is not
evidence of anything. `0.2.1` adds no flag and changes no API; the one behaviour
that did change is `publish --notify`, whose link now names the registry's
release-ping form instead of relying on a blank issue the registry has since
turned off.

If `--version` prints `0.2.0`, first run `which astra-plugin` (`where` on
Windows): the commonest cause is an older binary earlier on your `PATH`, and
`--version` alone cannot tell that apart from a fresh build of an older commit.
Then stop guessing from the number and read the pin instead — `init-ci` writes
the exact thing the bug was about, and it answers in one line.

This is the check that does not depend on the version at all:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

A build with the fix reports the pin `e3329df252a46d747676cb540ae4b986af68a3ad`
— a commit. A build without it reports `dc1a044876926e9cf1170f034e2eab533ec07641`,
which is the `plugin-release/v1` tag *object* and is what GitHub rejects. If you
see the second, reinstall from `master` with the line above and run `init-ci`
again. It is safe to re-run: it keeps your inputs and rewrites the pin. Nothing
is repaired in place, so an existing `release.yml` keeps the bad SHA until you
re-run it.

The command set, in full:

<!-- doctest: output from="astra-plugin --help" -->
```
Astra Plugin Development CLI

Usage: astra-plugin [OPTIONS] <COMMAND>

Commands:
  new      Create a new plugin project from a template
  dev      Start a plugin in dev mode (sideload into the running Astra + hot-reload)
  build    Build a plugin into a distributable .astraplugin bundle
  sign     Append the retiring in-ZIP SIGNATURE/PUBKEY pair to a built bundle
  verify   Verify a built .astraplugin bundle and print its digests
  test     Run the conformance suite against a real plugin process
  doctor   Answer, in one command, every question asked when a plugin will not start: toolchains, the daemon, the manifest, the entry point, permissions, the platform block, the release workflow
  logs     Read a plugin's output from the daemon that spawned it
  check    Check a plugin manifest, config schema and release workflow
  init-ci  Write .github/workflows/release.yml, pinned to a commit of the Astra reusable workflow. Re-run it to upgrade the pin; it keeps your inputs
  version  Set the version in plugin.toml and every other manifest at once
  publish  Get a release listed: preflight it, or open a prefilled submission
  keygen   Generate the OPTIONAL Ed25519 keypair `astra-plugin sign` uses
  help     Print this message or the help of the given subcommand(s)

Options:
      --json     Print one JSON document instead of human output. Progress lines are suppressed so the output is safe to pipe
  -h, --help     Print help
  -V, --version  Print version

Exit codes: 0 success · 1 the plugin/bundle is wrong · 2 the CLI could not run the check.
RUST_LOG controls trace output, e.g. RUST_LOG=astra_plugin=debug.
```

There is **no `astra-plugin login`**, and that is deliberate rather than
unfinished: nothing in this toolchain ever asks you for a credential. See
[Get listed](5-publish/get-listed.md).

## Keeping it current

Re-run the same `cargo install --git` line. Cargo replaces the binary in place.
There is no self-update, and there will not be one before there are signed
release binaries to update to.

## Things that go wrong

| Symptom | Cause |
|---|---|
| `Could not find` protoc` ` | `protoc` is not on `PATH`. See the table above |
| `feature `edition2024` is required` | Rust older than 1.85 |
| `astra-plugin: command not found` after a successful install | `~/.cargo/bin` is not on `PATH` |
| `error: could not find `Cargo.toml`` when you run `cargo install --path .` at the repository root | There is no workspace manifest at the root. Point `--path` at `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | An older `astra-plugin` is earlier on your `PATH`. `--version` will not tell you apart — run `which astra-plugin` (`where` on Windows) to see which file you are actually running |
| `invalid value workflow reference`, on your first tag push | The CLI that wrote `release.yml` predates `5b8ab22` and pinned a tag object. See [how to tell whether your build has the fix](#the-bug-that-breaks-a-first-release-and-how-to-tell-whether-your-build-has-the-fix) |

## Next

- **[What publishing is](publishing.md)** — the whole journey, empty directory
  to listed plugin, in one page.
- [Getting started](2-tutorial/getting-started.md) — writing the plugin itself.

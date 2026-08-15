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
toolchain. Shipping prebuilt `linux-x64` and `windows-x64` binaries is a known,
separate, pending task; until it lands, this page describes the whole of what
exists.

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

<!-- doctest: output from="PROTOC=/nonexistent/protoc cargo build --release -p astra-plugin-sdk" -->
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
it reports are whatever is on `master` when you run it — the angled placeholders
below are the two parts that differ on your machine:

<!-- doctest: output from="cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --root <scratch> --locked" -->
```
   Compiling astra-plugin-cli v<version> (/home/you/.cargo/git/checkouts/astraplugins-341ed6441d668bfa/<short-sha>/astra-plugin-cli)
    Finished `release` profile [optimized] target(s) in 23.60s
  Installing /home/you/.cargo/bin/astra-plugin
   Installed package `astra-plugin-cli v<version> (https://github.com/mihailinl/AstraPlugins#<sha>)` (executable `astra-plugin`)
```

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
astra-plugin 0.2.1
```

If the shell cannot find it, `cargo install` put it in `~/.cargo/bin` (or
`%USERPROFILE%\.cargo\bin` on Windows) and that directory is not on your `PATH`.
`cargo` prints a warning saying exactly that when it happens.

### Take 0.2.1 or newer, and why that matters

**`0.2.0` has a bug that breaks your first release.** `astra-plugin init-ci`
pinned an annotated tag's *object* SHA where GitHub requires a commit, so the
first `git push --tags` failed with `invalid value workflow reference` before any
job started. That was [AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2),
and it is fixed in `0.2.1`.

The awkward part, said plainly: `0.2.0` was published both before and after the
fix commit `5b8ab22`, so for a while the version could not tell a working build
from a broken one. `0.2.1` exists to end that. It adds no flag and changes no API; the one
behaviour that did change is `publish --notify`, whose link now names the
registry's release-ping form instead of relying on a blank issue the registry
has since turned off.

If `--version` prints `0.2.0`, run `which astra-plugin` (`where` on Windows)
first: the usual cause is an older binary earlier on your `PATH`, and `--version`
alone cannot tell the two apart. If that path is the one you just installed and
the number is still `0.2.0`, then the `master` you built from does not carry
`0.2.1` yet — the fix commit `5b8ab22` landed on `master` before the version bump
that names it, so a build can have the fix and still say `0.2.0`. Do not guess
either way: the `init-ci` check below reads the pin the CLI actually writes, which
is the thing the bug was about.

You can also confirm it without trusting the version at all, by looking at what
`init-ci` writes:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

A fixed build reports the pin `e3329df252a46d747676cb540ae4b986af68a3ad` — a
commit. A `0.2.0` build reports `dc1a044876926e9cf1170f034e2eab533ec07641`, which
is the tag object and is what GitHub rejects. `init-ci` is safe to re-run: it
keeps your inputs and rewrites the pin. Nothing is repaired in place, so an
existing `release.yml` keeps the bad SHA until you re-run it.

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
| `invalid value workflow reference`, on your first tag push | The CLI that wrote `release.yml` was `0.2.0` and pinned a tag object. See [take 0.2.1 or newer](#take-021-or-newer-and-why-that-matters) |

## Next

- **[What publishing is](publishing.md)** — the whole journey, empty directory
  to listed plugin, in one page.
- [Getting started](2-tutorial/getting-started.md) — writing the plugin itself.

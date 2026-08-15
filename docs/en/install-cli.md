# Install the CLI

Everything in the publishing path starts with a command, and this is the page
that gets you the command. The binary is called **`astra-plugin`** — not
`astra-plugin-cli`, which is only the crate's name.

## Two ways, and which one you want

**Download the binary.** Release [`cli-v0.2.1`][rel] carries prebuilt archives
for Linux and Windows, a checksum file, and a Sigstore bundle you can verify.
Nothing needs to be compiled and no toolchain is involved. This is the path most
people want, and it is the one below.

**Or build from source**, which needs Rust 1.85 or newer and `protoc`. Take this
one if you are on a platform with no archive — macOS and ARM Linux, today — or
if you want to read or change the CLI as well as run it.

**`cargo install astra-plugin-cli` is not one of the ways, and will not work.**
The crate depends on a vendored `astra-plugin-manifest` by path
(`astra-plugin-manifest = { path = "vendor/astra-plugin-manifest" }`), cargo
never packages a path dependency's source, and publishing therefore fails with
*all dependencies must have a version requirement specified* — so the crate is
not on crates.io at all (`https://index.crates.io/as/tr/astra-plugin-cli`
answers `404` today, while `astra-plugin-sdk` at the same index answers `200`).
Unblocking it means releasing the manifest crate from Astra first, and this page
promises no date for that.

[rel]: https://github.com/mihailinl/AstraPlugins/releases/tag/cli-v0.2.1

## Download a binary

### Which archive

| You are on | Take |
|---|---|
| **Any Linux** | `astra-plugin-0.2.1-linux-x64-musl.tar.gz` |
| Linux, and you specifically want the glibc build | `astra-plugin-0.2.1-linux-x64-gnu.tar.gz` |
| **Windows** | `astra-plugin-0.2.1-windows-x64.zip` |

**musl is the safe default, and the reason is not taste.** The gnu build is
dynamically linked and its symbol table requires **glibc 2.39 or newer**, which
Ubuntu 22.04 (2.35), Debian 12 (2.36) and RHEL 9 (2.34) do not have — on any of
those it fails to start rather than misbehaving subtly. The musl archive is a
`static-pie` executable with no libc dependency at all, so it runs on every one
of them. Take gnu only if you know you want it.

The full asset list on that release, which is everything published:

<!-- doctest: output from="gh release view cli-v0.2.1 --repo mihailinl/AstraPlugins --json assets" unrun="reads a GitHub release over the network; re-run the command in the from= to confirm the list, or open the release page" -->
```
astra-plugin-0.2.1-linux-x64-gnu.tar.gz     3372607
astra-plugin-0.2.1-linux-x64-musl.tar.gz    3425289
astra-plugin-0.2.1-windows-x64.zip          3450755
SHA256SUMS.txt                                  314
astra-plugin-0.2.1.sigstore.jsonl             11414
```

### Get it and check it

Linux, using `curl` — nothing here needs `gh` or a GitHub account:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1-linux-x64-musl.tar.gz
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/SHA256SUMS.txt
sha256sum -c --ignore-missing SHA256SUMS.txt
tar xzf astra-plugin-0.2.1-linux-x64-musl.tar.gz
./astra-plugin-0.2.1-linux-x64-musl/astra-plugin --version
```

That is a real transcript of those commands:

<!-- doctest: output from="sha256sum -c --ignore-missing SHA256SUMS.txt" unrun="needs the release archive downloaded next to the checksum file; re-run the two curl lines above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
```

**Use `--ignore-missing`.** `SHA256SUMS.txt` lists all three archives, so a
plain `sha256sum -c SHA256SUMS.txt` reports the two you did not download as
`FAILED open or read` and **exits 1** — which looks exactly like a corrupted
download and is not one:

<!-- doctest: output from="sha256sum -c SHA256SUMS.txt" unrun="needs one of the three archives present and the other two absent; re-run the curl lines above and then this one to reproduce it" -->
```
sha256sum: astra-plugin-0.2.1-linux-x64-gnu.tar.gz: No such file or directory
astra-plugin-0.2.1-linux-x64-gnu.tar.gz: FAILED open or read
astra-plugin-0.2.1-linux-x64-musl.tar.gz: OK
sha256sum: astra-plugin-0.2.1-windows-x64.zip: No such file or directory
astra-plugin-0.2.1-windows-x64.zip: FAILED open or read
sha256sum: WARNING: 2 listed files could not be read
```

The archive unpacks into a directory holding the binary and its licence files:

<!-- doctest: output from="tar tzf astra-plugin-0.2.1-linux-x64-musl.tar.gz" unrun="needs the downloaded archive; re-run the curl line above and then this one" -->
```
astra-plugin-0.2.1-linux-x64-musl/
astra-plugin-0.2.1-linux-x64-musl/LICENSE
astra-plugin-0.2.1-linux-x64-musl/NOTICE
astra-plugin-0.2.1-linux-x64-musl/README.md
astra-plugin-0.2.1-linux-x64-musl/astra-plugin
```

Move `astra-plugin` somewhere on your `PATH` — `~/.local/bin` is the usual
answer, and it needs no `sudo`:

<!-- doctest: cli -->
```bash
mkdir -p ~/.local/bin
cp astra-plugin-0.2.1-linux-x64-musl/astra-plugin ~/.local/bin/
astra-plugin --version
```

On Windows, download the `.zip` from the release page, unzip it, and put
`astra-plugin.exe` on your `PATH`. `certutil -hashfile <file> SHA256` is the
built-in checksum tool, and its output is compared against `SHA256SUMS.txt` by
eye.

### Verify who built it

The checksum proves the bytes match a file the release names. It does not prove
who produced that file — for that there is a Sigstore bundle, and `gh` checks it
against GitHub's build attestation:

<!-- doctest: cli -->
```bash
curl -fsSLO https://github.com/mihailinl/AstraPlugins/releases/download/cli-v0.2.1/astra-plugin-0.2.1.sigstore.jsonl
gh attestation verify astra-plugin-0.2.1-linux-x64-musl.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins
astra-plugin --version
```

**A pass prints nothing when output is not a terminal, and exits `0`.** That is
disconcerting the first time; check `echo $?` rather than looking for a tick.
A failure is loud and exits `1`:

<!-- doctest: output from="gh attestation verify tampered.tar.gz --bundle astra-plugin-0.2.1.sigstore.jsonl --repo mihailinl/AstraPlugins" unrun="needs the bundle and a deliberately corrupted copy of the archive; append a byte to the archive and re-run to reproduce it" -->
```
Error: verifying with issuer "sigstore.dev"
```

That was produced by appending one byte to the archive; pointing `--repo` at a
repository that did not build it fails identically. One bundle covers all three
archives, and what it attests to is readable with `--format json`: the signing
workflow is
`https://github.com/mihailinl/AstraPlugins/.github/workflows/release-cli.yml@refs/tags/cli-v0.2.1`,
the issuer is `https://token.actions.githubusercontent.com`, and the three
subject digests are the three lines of `SHA256SUMS.txt`. `gh attestation verify`
needs network access to fetch the trust root, but not a GitHub login.

## Build from source

Take this path for macOS or ARM Linux, where there is no archive yet, or to work
on the CLI itself. It is not a fallback for a failed download — the binary above
is the same program.

### Prerequisites

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

### Build it

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

To build the exact code the released binaries were built from rather than
whatever `master` carries today, check out the release tag first:

<!-- doctest: cli -->
```bash
git clone --branch cli-v0.2.1 https://github.com/mihailinl/AstraPlugins
cargo install --path AstraPlugins/astra-plugin-cli --locked
astra-plugin --version
```

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

A downloaded binary prints `astra-plugin 0.2.1`, because the archive is built
from the `cli-v0.2.1` tag and nothing else. `<version>` is a placeholder only on
the source path: `cargo install --git` builds whatever `master` carries at that
moment, so what you get is the version in that commit's `Cargo.toml`, which may
be ahead of the newest release. `0.2.1` is the newest entry in
[the CLI's changelog](../../astra-plugin-cli/CHANGELOG.md).

If the shell cannot find it: a downloaded binary is wherever you copied it, and
`cargo install` puts one in `~/.cargo/bin` (or `%USERPROFILE%\.cargo\bin` on
Windows). Either way that directory is not on your `PATH`. `cargo` prints a
warning saying exactly that when it happens.

### The bug that breaks a first release, and how to tell whether your build has the fix

**`astra-plugin init-ci` used to pin an annotated tag's *object* SHA where GitHub
requires a commit**, so the first `git push --tags` failed with `invalid value
workflow reference` before any job started. That was
[AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2).

**Downloading the `0.2.1` binary settles this, and is the short answer.** The
archive is built from the `cli-v0.2.1` tag, `5b8ab22` is an ancestor of it, so a
downloaded binary has the fix. The rest of this section is for a build from
source, where the number does not settle it.

**The fix is commit `5b8ab22`, not a version number**, and this is the part that
catches people out. A source build installs whatever commit you cloned rather
than a chosen release. `5b8ab22` landed on `master` *before* the bump that
raised the number to `0.2.1`, which means:

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

If you downloaded a binary, download the next release's archive and replace the
file — check the checksum again, since a new release means new bytes. If you
built from source, re-run the same `cargo install` line and cargo replaces the
binary in place. **There is no self-update**, and nothing in this toolchain
phones home to discover that a new version exists.

## Things that go wrong

| Symptom | Cause |
|---|---|
| `FAILED open or read` from `sha256sum -c` | You downloaded one archive and the file lists three. Add `--ignore-missing` |
| `Error: verifying with issuer "sigstore.dev"` | The archive does not match the bundle, or `--repo` names a repository that did not build it. Re-download rather than reasoning about it |
| `gh attestation verify` printed nothing at all | That is a pass. It is quiet when output is not a terminal; `echo $?` shows `0` |
| The binary will not start, and the loader complains that a `GLIBC_2.39` version was not found | You took the gnu archive on a system with older glibc. Take the musl one; it needs no libc |
| `error: could not find `astra-plugin-cli` in registry `crates-io` with version `*`` | `cargo install astra-plugin-cli` cannot work, and this is what it says. See the top of this page |
| `Could not find` protoc` ` | `protoc` is not on `PATH`. See the table above |
| `feature `edition2024` is required` | Rust older than 1.85 |
| `astra-plugin: command not found` after a successful install | The directory holding the binary is not on `PATH` — `~/.cargo/bin` for a source build |
| `error: could not find `Cargo.toml`` when you run `cargo install --path .` at the repository root | There is no workspace manifest at the root. Point `--path` at `astra-plugin-cli/` |
| `unrecognized subcommand 'new'` | An older `astra-plugin` is earlier on your `PATH`. `--version` will not tell you apart — run `which astra-plugin` (`where` on Windows) to see which file you are actually running |
| `invalid value workflow reference`, on your first tag push | The CLI that wrote `release.yml` predates `5b8ab22` and pinned a tag object. See [how to tell whether your build has the fix](#the-bug-that-breaks-a-first-release-and-how-to-tell-whether-your-build-has-the-fix) |

## Next

- **[What publishing is](publishing.md)** — the whole journey, empty directory
  to listed plugin, in one page.
- [Getting started](2-tutorial/getting-started.md) — writing the plugin itself.

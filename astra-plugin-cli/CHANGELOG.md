<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# Changelog — `astra-plugin-cli`

All notable changes to this crate. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

**This crate ships as binaries, from its own tag.** `cli-v<VERSION>` runs
[`.github/workflows/release-cli.yml`](../.github/workflows/release-cli.yml),
which builds linux-x64 (musl + gnu) and windows-x64 archives, attests them and
publishes a GitHub Release — separately from the three SDKs, which ship together
from one `sdk-v<VERSION>` tag. It is **not** on crates.io and cannot be until the
vendored `astra-plugin-manifest` crate is published; `cargo install --git` and
the archives are the two supported paths
([`docs/en/install-cli.md`](../docs/en/install-cli.md)). Either way **the version
below is the only thing that tells one build from another**, which is why a
one-line fix gets a version bump here.

This paragraph used to say the opposite — "no release train, no prebuilt
binaries, no git tag cuts a CLI release". `release-cli.yml` landed in `e3bd6c7`
and `cli-v0.2.1` was pushed 47 minutes later, on 2026-08-15; the paragraph was
not part of either commit and stayed false for eight days, in the file an author
reads to find out how to get the tool.

## [0.3.0] — unreleased

The whole `astra-plugin locale` command group, two new pack-time refusals, and
a bundle-size cap that answers before the tag instead of after it.

**0.3.0 and not 0.2.2, because `build` now refuses bundles it used to pack.**
A `plugin.toml` that shipped under the 0.2.1 archives can fail `check` and
`build` today: E20 refuses a `$key` in `[plugin] name`/`description`, E21
refuses a `$key` whose English value is the empty string, and the artifact cap
refuses a `.astraplugin` the registry would not list. `locales.lock.json`
changed shape too. Per
[`docs/en/versioning.md`](../docs/en/versioning.md)'s 0.x reading — *minor may
break source compatibility, patch is bug fixes and additions only* — "your
build can start failing" is the minor slot. The `locale` group and the seeded
scaffold are additions and would have been a patch on their own.

### Added

- **`astra-plugin locale`** — `ls`, `add <code> [--prune]`, `sync [--accept]`,
  `check`, `extract`, `render [--lang]`, `pseudo`. `locales/` had rules that
  `astra-plugin check` and `build` enforced and no command helped you satisfy;
  these are that command. `ls` always prints how many codes
  `spec/locales.yaml` declares beside how many this plugin ships, so an empty
  result reads as empty rather than as a pass.
- **`astra-plugin new` seeds `locales/en.json` and `locales.lock.json`.** A
  directory that exists gets edited; one you have to learn about from a
  document does not. The lock goes at the project root, not inside `locales/`,
  because every top-level `*.json` in there is loaded as a locale keyed on its
  stem — `locales/locales.lock.json` would become a phantom locale called
  `locales.lock`.

### Changed (breaking)

- **`[E20]` — `[plugin] name` or `description` beginning with `$`.** The
  registry derives the store card from the PACKED `plugin.toml`, unresolved,
  and `MANIFEST.json` carries the same bytes, so a `$key` here is the literal
  text a user reads on the card — on every Astra that has ever existed,
  including ones that resolve keys perfectly well elsewhere. Not gated on
  `min_astra_version`, because the reader that breaks is not a daemon. Write
  English there and put the translation under `listing.name` /
  `listing.description` in `locales/<code>.json`.
- **`[E21]` — a `$key` whose `locales/en.json` value is the empty string.** An
  empty value is a *translation*, not a miss, so the daemon renders it: the
  label disappears, in every language, because the other nine fall back per key
  to English and English is the blank. `locale extract` prints a paste block;
  pasting it unedited is how a plugin got here.
- **`build` refuses a bundle over the registry's artifact cap**, and warns at
  half of it. A 300 MiB bundle previously packed, tagged, uploaded, and was
  refused *after* the tag — at the one point in a release where nothing can be
  taken back.
- **`locales.lock.json` changed shape**: every key gets an entry now, seeds
  included, and the lock covers the plural rows a language needs that English
  cannot carry. A lock written by 0.2.1 is rewritten by the first `sync` after
  the upgrade.

### Fixed

- **`astra-plugin locale sync` recorded an untranslated seed as a fresh
  translation, and the registry published your previous English as your Russian
  store card.**

  What you saw: nothing. `astra-plugin locale add ru` seeds `ru.json` with the
  English, which is the intended starting point. You then edited your
  description, `check` said `[E8] … Fix: astra-plugin locale sync`, and you ran
  it. `locale ls` said `stale 0`, `check` said OK, `build` packed it, the
  release went green — and the card in the catalogue carried the sentence you
  had just rewritten, in Russian and Japanese, for as long as nobody looked.

  Why: a value equal to English got **no lock entry**. So on the next `sync` the
  seed matched "differs from English, and the lock has never seen it", which was
  read as *newly translated* and stamped with the digest of the **new** English.
  Both sides then agreed the translation was current: the CLI's `[N3]` compares
  that digest, and so does the ingest bot's `W_LOCALE_STALE`. There was no
  finding anywhere, on either side of the tag.

  Now **every key gets an entry, including one whose value is still English** —
  a seed is a copy of a sentence, and a copy is the thing an edit has to be able
  to invalidate. A seed the English has moved out from under is `[N15]`, a new
  note that says what it is rather than calling it a stale translation; it is a
  note at both gates, because the reader gets English either way and refusing a
  release over a file nobody claimed to have translated is a different trade
  from refusing one over a confidently wrong Russian sentence.

  In the same mechanism: the lock now covers a plural row a language needs and
  English cannot carry. `ru`'s `few` and `many` are measured against
  `<base>.other`, so rewriting both English rows of a four-row Russian family
  reports **four** stale and not two — it reported two, `--accept` cleared it,
  and the family shipped two-thirds updated and reading fresh.

  **One thing to check once, on a plugin you started before this build.** A lock
  written by an older `astra-plugin` has no entry for its seeds, so the first
  `sync` after this upgrade still has no evidence for a value that differs from
  today's English and has never been recorded — it stamps it as a translation,
  exactly as before. Run `astra-plugin locale sync` once and read what it
  reports; from that point the lock is complete and an English edit ages the
  seeds like everything else.

### Note for maintainers

Bumping this version makes `docs/en/reference/cli.md` stale — it is generated
from the binary and embeds `astra-plugin 0.3.0` in two places. Run
`cargo build --release --manifest-path astra-plugin-cli/Cargo.toml` and then
`python3 tools/docgen/gen.py`, and commit the result with this change. CI runs
`python3 tools/docgen/gen.py --check` and fails otherwise. The six translated
`docs/<locale>/reference/cli.md` carry the same two strings and `gen.py` does
not write them; substitute them by hand, as this commit did.

## [0.2.1] — 2026-08-15

### Fixed

- **`astra-plugin init-ci` pinned a tag object where a commit was required, so
  every author's first release failed.**

  What you saw: `init-ci` wrote `.github/workflows/release.yml` and looked
  correct. The first `git push --tags` then failed in GitHub Actions before any
  job started — the run went red immediately, nothing was built, and the failure
  named the `uses:` line: GitHub reports it as an **invalid workflow reference**
  (it cannot find a workflow at that SHA, because that SHA is not a commit).
  `init-ci`'s own printed note warns about `invalid value workflow reference`,
  and the tool that wrote the warning was causing it.

  Why: the pin is resolved with `git ls-remote <url> refs/tags/plugin-release/v1`.
  An exact refspec returns exactly that ref and nothing else. `plugin-release/v1`
  is an **annotated** tag — the kind a real release carries, because it has a
  message — and an annotated tag's ref points at the *tag object*, whose SHA is
  not a commit. `uses: owner/repo/.github/workflows/x.yml@<sha>` takes a commit.
  The lookup now asks for `refs/tags/<t>` **and** `refs/tags/<t>^{}`, the peeled
  line, and prefers the peeled one whichever order the remote sends them in.

  It hid because a *lightweight* tag points straight at the commit, so the
  one-pattern lookup was right and nothing looked wrong. Every test and every
  earlier run had no release tag at all and fell through to the default-branch
  head, which is also a commit.

  Landed in `5b8ab22`, which is on `master`. Reported as
  [AstraPlugins#2](https://github.com/mihailinl/AstraPlugins/issues/2).

  **The remedy is to rebuild the CLI and re-run `init-ci`.** Nothing is fixed in
  place: an existing `release.yml` still carries the bad SHA in its `uses:`
  line, and `init-ci` is safe to re-run — it keeps your inputs and rewrites the
  pin.

  ```bash
  cargo install --path astra-plugin-cli     # from a clone; or --git, see the docs
  astra-plugin --version                    # must print 0.2.1
  astra-plugin init-ci .                    # rewrites the pin, keeps your inputs
  ```

  If `--version` still prints `0.2.0`, you are running the old binary — an
  earlier `cargo install` left it ahead of the new one on `PATH`.

- **`astra-plugin publish --notify` produced a link that lost everything it had
  prefilled.**

  The listing link has always named an issue template; the ping link did not —
  it was a plain `issues/new?title=…&body=…`. That worked only while the
  registry accepted blank issues. It no longer does: `astra-registry`'s
  `.github/ISSUE_TEMPLATE/config.yml` sets `blank_issues_enabled: false`, and
  GitHub answers a blank-issue URL by redirecting to `/issues/new/choose` and
  **discarding every query parameter on the way**. The author got an empty
  template picker, had to work out for themselves that they wanted *"A release
  of a plugin that is already listed"*, and had to retype the `/release` line
  the tool had just written for them.

  The link now names `release-ping.yml` and fills that form's one field:

  ```
  …/issues/new?template=release-ping.yml&title=…&command=…
  ```

  `command` is the textarea's `id`, which is how GitHub prefills a form. The
  `/release owner/repo <tag>` line stays first inside it, because the registry's
  `firstWrittenLine` skips the `### <label>` heading and blank line GitHub's own
  renderer inserts and nothing else.

  `--dry-run` and the listing link are unchanged.

### Changed

- Version bumped to `0.2.1` so a fixed build is distinguishable — `0.2.0`
  shipped both before and after `5b8ab22`, which is why the reporter of `#2`
  could not tell whether their rebuild had taken — and because `--notify` now
  emits a different URL. There is no flag or API change: the same command with
  the same arguments does the same thing, at an address that still works.

### Note for maintainers

Bumping this version makes `docs/en/reference/cli.md` stale — it is generated
from the binary and embeds `astra-plugin 0.2.1` in two places. Run
`cargo build --release --manifest-path astra-plugin-cli/Cargo.toml` and then
`python3 tools/docgen/gen.py`, and commit the result with this change. CI runs
`python3 tools/docgen/gen.py --check` and fails otherwise.

## [0.2.0] — unreleased

Breaking, against 0.1.x scripts.

### Changed (breaking)

- `validate` became **`check`**, and `create` became **`new`**.
- `dev` no longer spawns the plugin itself. It asks the running Astra daemon to
  sideload it, so the plugin registers and behaves as an installed one does.
  `--standalone` keeps the old spawn-it-directly behaviour, and prints a note
  saying the plugin cannot register with Astra that way.

## [0.1.x]

Earlier development; see git history.

<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# Changelog — `astra-plugin-cli`

All notable changes to this crate. Format roughly follows
[Keep a Changelog](https://keepachangelog.com/), versions follow
[SemVer](https://semver.org/).

**This crate has no release train.** It is not published to crates.io, there
are no prebuilt binaries, and no git tag cuts a CLI release — unlike the three
SDKs, which ship together from one `sdk-v<VERSION>` tag. The only way to get
the tool is to build it from a clone
([`docs/en/install-cli.md`](../docs/en/install-cli.md)), so **the version below
is the only thing that tells one build from another.** That is why a one-line
fix gets a version bump here.

## [0.2.1] — unreleased

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

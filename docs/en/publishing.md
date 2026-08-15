# Publishing a plugin

**One page, from an empty directory to a plugin users can install.** Every
command is here in order, with the output it produces. If you read exactly one
page about publishing, read this one; the deeper pages are linked where they
matter and none of them is required to finish.

---

## Read this part even if you read nothing else

Publishing a plugin to Astra means **one specific thing**: you tag a release in
your own GitHub repository, GitHub's CI builds the bundle and attests it, and
you send the registry one listing request — once, ever.

These are **not** publishing, and each of them has been tried:

| Not publishing | Why it cannot work |
|---|---|
| Pushing your source to GitHub | The registry never reads your source tree. It reads a `.astraplugin` file attached to a release, and there isn't one |
| Sending someone a `.zip`, or a bundle you built on your laptop | The bytes carry no build attestation, so the registry refuses them however good the plugin is |
| Opening an issue asking a maintainer to build it for you | Nobody builds your plugin but your repository's own CI. There is no other builder |
| Opening an issue on the registry that describes your plugin, outside the listing form | Only the form applies the `listing` label, and only that label starts an ingest. Blank issues are off there now, and an unlabelled request gets a reply naming the label rather than silence — but a reply is not a listing. See [Submit](#8-submit-once-ever) |

**Why it has to be that way, in two sentences.** The registry pins your plugin
by the SHA-256 of the exact file a user will download, and it reads GitHub's
build attestation — a Sigstore signature minted from the workflow's own OIDC
identity — which states that these exact bytes came out of that workflow, at
that commit, in that repository. A file you built on your laptop and handed to
somebody carries neither of those, so there is nothing for Astra to check on the
user's machine and nothing for the registry to pin.

None of it is a claim that your code is safe. See
[What establishes trust](#what-establishes-trust) at the bottom of this page.

---

## Before you start

<!-- doctest: cli -->
```bash
astra-plugin --version
```

If that prints nothing, stop here and do **[Install the CLI](install-cli.md)**
first. It is one `cargo install` line, it needs a Rust toolchain, and there are
no prebuilt binaries yet — that page says so plainly and tells you what to
install.

> **Take `0.2.1` or newer.** `0.2.0` writes a release workflow that GitHub
> rejects the moment you push your first tag, so a `0.2.0` build cannot finish
> this page. If `--version` says `0.2.0`, re-run the `cargo install` line on
> [Install the CLI](install-cli.md) before going further.

You also need a **public** GitHub repository. Attestations are published to a
public transparency log; on a private repository they need GitHub Enterprise,
and the release workflow will tell you so rather than quietly producing
unattested bundles.

---

## 1 · Scaffold

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller" -->
```
Created plugin project 'dice-roller' at dice-roller/
Language: rust
Template: tool
Capabilities: tools

Next steps:
  cd dice-roller
  cargo build --release
  astra-plugin test .
  astra-plugin dev .
```

`--lang python` and `--lang typescript` scaffold the other two SDKs; `--template`
picks what you start from (`tool`, `tts`, `stt`, `stt-streaming`, `ai-provider`,
`ui`, `action-trigger`, `client`, `blank`). Writing the plugin itself is
[Getting started](2-tutorial/getting-started.md) and the
[SDK pages](4-sdk/rust.md).

**Fill in two fields in `plugin.toml` before you go further.** The scaffold
leaves `author` empty and `description` generic, and both end up on your store
card:

<!-- doctest: illustrative reason="a fragment of the scaffolded plugin.toml showing the two fields to edit; a complete manifest is checked by the toml-manifest block in reference/manifest.md" -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "An Astra plugin"     # ← what a person reads on the card
author = ""                         # ← fill this in
license = "MIT"                     # ← must be on the registry's SPDX allowlist
```

The `icon.svg` the scaffold writes is a placeholder; replacing it is
[Get listed §what your listing will look like](5-publish/get-listed.md#what-your-listing-will-look-like).

## 2 · Prove it runs

<!-- doctest: cli -->
```bash
astra-plugin test .
```

This is the conformance suite, run against your plugin as a **real process**
talking to a mock daemon — not against a type in your test file. Truncated to
its verdict:

<!-- doctest: output from="astra-plugin test ." -->
```
  Registered: port 37173, protocol 1, sdk astra-plugin-sdk-rust 0.6.0
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] CallTool                 required  `hello` answered
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 42.1ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 837.6µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] a call without the daemon's token is refused: HealthCheck without `x-plugin-token` answered UNAUTHENTICATED
  [ok  ] Shutdown is honoured within the grace period: the process exited 42.1ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 1 host call(s) reached the daemon: log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 6 hook(s) exercised, 7 check(s) passed.
```

To drive it inside a running Astra instead, `astra-plugin dev .` — that is
[sideloading](5-publish/sideload.md), the authoring loop, and it is **not** a way
to give the plugin to anybody else.

## 3 · Set up the release workflow

You write no YAML. One command does it:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

<!-- doctest: output from="astra-plugin init-ci" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned e3329df252a46d747676cb540ae4b986af68a3ad (plugin-release/v1)
    with   plugin-dir: .
           tag-prefix: v

  Next: commit this file, then release with
    astra-plugin version <semver>
```

That commit SHA is not decoration. It is the released reusable workflow
`plugin-release/v1` points at, and it is one of the SHAs the registry's
root-signed `trust.json` allows — a build produced by any other workflow is
refused with `E_WORKFLOW_NOT_ALLOWED`. Re-run `init-ci` any time to move the pin
forward; it keeps the inputs you set.

**Check the SHA it printed before you go on.** It must be
`e3329df252a46d747676cb540ae4b986af68a3ad`. If it is
`dc1a044876926e9cf1170f034e2eab533ec07641`, you are on CLI `0.2.0`: that is the
*tag object's* SHA, and `uses: …@<sha>` needs a commit, so your first
`git push --tags` fails with `invalid value workflow reference` before any job
starts. Re-run the `cargo install` line on [Install the CLI](install-cli.md),
then run `astra-plugin init-ci` again — it rewrites the pin and keeps your
inputs. Nothing is repaired in place, so an existing `release.yml` keeps the bad
SHA until you re-run it. This is the bug that broke a real author's first
release.

Detail, including what the generated file contains and why each of its three
permissions is required: [Release with CI](5-publish/release-with-ci.md).

<!-- doctest: cli -->
```bash
astra-plugin check --strict
```

<!-- doctest: output from="astra-plugin check --strict" -->
```
Checking plugin at ....
  NOTE: Missing plugin.author
  NOTE: Pin freshness not checked (pass --resolve-pin, or set ASTRA_PLUGIN_WORKFLOW_SHA)
  sections: [plugin], [entry], [capabilities]
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
```

`--fix` applies whatever can be fixed mechanically. `--resolve-pin` asks GitHub
whether your workflow pin is still the current one; it is off by default so that
neither `dev` nor CI needs the network to run a check.

## 4 · Push it, public

<!-- doctest: cli -->
```bash
git init && git add -A && git commit -m "dice-roller 0.1.0"
git remote add origin https://github.com/you/dice-roller
git push -u origin main
astra-plugin check --strict
```

Nothing about this step is special — it is an ordinary repository. But note what
it is *not*: pushing this is not publishing the plugin, and stopping here is
where the two real submissions that prompted this page went wrong. What makes it
a published plugin is the tag in the next step.

## 5 · Tag — this is the release

<!-- doctest: cli -->
```bash
astra-plugin version 0.1.0
git commit -am "release 0.1.0"
git tag v0.1.0
git push && git push --tags
```

<!-- doctest: output from="astra-plugin version 0.2.0" -->
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

`astra-plugin version` rewrites `plugin.toml` **and** every other manifest in the
project in one edit — `Cargo.toml`, `package.json`, `pyproject.toml` — so they
cannot disagree. It refuses a version that sorts below the current one unless you
pass `--allow-downgrade`, because Astra refuses to install a downgrade and such a
release would be uninstallable.

**The tag is the whole release process.** Pushing it starts your
`release.yml`, which calls the pinned reusable workflow, which runs three jobs
— a `plan` job that reads your manifest as data and never runs your code, a
`build` matrix that runs your code and holds no write token, and a `publish`
job that re-derives every digest itself and attests what it hashed. That split
is the security property, and it is described in
[Release with CI §3](5-publish/release-with-ci.md#3-what-ci-does).

When it finishes, your GitHub Release carries:

<!-- doctest: illustrative reason="the asset names a release ends up with; they are produced by GitHub Actions in the author's own repository, so there is no local command that emits this listing" -->
```
dice-roller-0.1.0-linux-x64.astraplugin
dice-roller-0.1.0-windows-x64.astraplugin
dice-roller-0.1.0.sigstore.jsonl
SHA256SUMS.txt
```

The Release becomes visible only once every asset is attached. Rust plugins get
one file per platform; TypeScript and Python get a single `noarch` file.

**If the workflow did not run at all**, the usual cause is that
`on: push: tags:` and `tag-prefix:` disagree — a glob narrower than the prefix
never fires. The rest of the failure modes are in
[Release with CI §things that go wrong](5-publish/release-with-ci.md#things-that-go-wrong).

## 6 · Check the release yourself

Anyone can, without trusting Astra or the registry:

<!-- doctest: cli -->
```bash
gh release download v0.1.0 --repo you/dice-roller --pattern "*.astraplugin"
gh attestation verify dice-roller-0.1.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" -->
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

`astra-plugin verify` exits **1** when the bundle is wrong and **2** when the CLI
could not answer — a missing file, for instance. The archive format and what a
verifier must reject is [`spec/bundle-v2.md`](spec/bundle-v2.md).

## 7 · Preflight the listing

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

It runs every registry check that can be run locally, and then — the half that
matters — names the ones only the registry can run, so you know what is still
unproven:

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the release assets are served from your repository's own release namespace
  · that you have admin or maintain on the repository
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan

  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code
  each failure produces. What happens to a release that passes — published now,
  delayed 24 hours, or held for a person — is docs/POLICY.md.
```

## 8 · Submit, once ever

<!-- doctest: cli -->
```bash
astra-plugin publish
```

It opens a **prefilled issue on the registry** in your browser. It uploads
nothing and holds no credential — there is no `astra-plugin login`, no token in
your shell history, no keyring to integrate with. `--print-url` prints the link
instead of opening a browser:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" -->
```
dice-roller 0.1.0 — listing request for you/dice-roller@v0.1.0

  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI
  build and attest, and the registry picks it up. Everything on the store card —
  name, summary, licence, capabilities, permissions, digests — is read out of the
  attested bundle, so there is nothing else to fill in and nothing to keep in sync.

https://github.com/mihailinl/astra-registry/issues/new?template=plugin-listing.yml&title=%5Blisting%5D+you%2Fdice-roller&repository=you%2Fdice-roller&release_tag=v0.1.0
```

> **Use that link.** The `template=plugin-listing.yml` in it is load-bearing:
> the issue template declares `labels: ["listing", "needs-triage"]`, and the
> registry's bot only enters the submission path for an issue carrying the
> `listing` label. Nothing else applies it — not even the bot, deliberately,
> because in that repository the label is an authority token rather than a
> category.
>
> That used to fail silently. Two requests from a real author arrived with no
> labels, triage returned `mode: "none"`, the check, publish and comment steps
> were all skipped, and **they got no answer at all, not even a refusal** —
> which is the reason this page exists. Both halves are closed now: the registry
> disables blank issues, so the form is the only door, and a request that still
> arrives unlabelled gets a comment naming the label and the single click that
> starts verification on that same issue. Use the link anyway: it is the path
> that starts an ingest without anybody having to intervene.

The submission carries **two facts**: your source repository (`you/dice-roller`)
and the release tag (`v0.1.0`), plus two confirmations — that you own or maintain
the repository, and that you have read the policy. Everything else is read out of
the attested bundle, because everything in the bundle is covered by the
attestation and is therefore worth strictly more than anything typed into a form.

## 9 · What happens next

Detail, including every reason code: [Get listed §what happens after you
submit](5-publish/get-listed.md#3-what-happens-after-you-submit). The short
version:

| Outcome | Means | Who is involved |
|---|---|---|
| **Published** | Committed, and in the catalogue on the next index build | nobody |
| **Delayed** | Everything passed; it publishes itself at a stated time | nobody |
| **Held** | A decision the registry is not entitled to make automatically | a maintainer, within **48 h** |
| **Refused** | A check failed | you: fix it and comment `/recheck` on the issue |

**A first listing is always held for a person** — that is one of exactly three
events that need one, along with a newly requested high-risk permission and a
change of repository. 48 hours is the published SLA for all of them.

A hold is cleared by a maintainer commenting `/approve` on your issue, which
re-runs every check from scratch rather than trusting anything cached. You do
not type that command and you need do nothing while you wait. See
[how a hold is cleared](5-publish/get-listed.md#how-a-hold-is-cleared).

The bot comments on your issue with the outcome and the reason either way — and
it now comments even when it is *not* going to start, which is the failure step
8 describes. If nothing has commented within an hour, check the `listing` label.
If it is missing, ask a maintainer to add it: labelling fires the same event a
new submission does, so verification starts on that issue with nothing to
retype.

## 10 · Every release after that

Nothing. Tag, and CI does the rest; the registry notices the release and
regenerates the index.

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

If the registry has not noticed within a few minutes:

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

That is the manual ping for a plugin that is **already listed**. Without
`--notify`, `publish` opens a first-listing request instead, which is not what
you want on your second release.

---

## What establishes trust

`astra-plugin build` links here, so the answer lives at this anchor until that
link moves.

**Not any key you hold.** `astra-plugin keygen` and `astra-plugin sign` produce
an optional second factor — useful against a GitHub account takeover, because the
key lives somewhere a stolen GitHub session is not. Astra does not verify it
against your key: the daemon checks the in-ZIP `SIGNATURE`/`PUBKEY` pair against
a *pinned Astra publisher key*, so a bundle signed with your own key is untrusted
in exactly the way an unsigned one is. Both the command and the format entries it
writes are being retired.

**What Astra actually acts on** is a registry record that countersigns the
SHA-256 of the whole file, and — checked by the registry bot at ingest, not by
the daemon — GitHub's build attestation saying which workflow, at which commit,
in which repository produced those bytes.

**How far the chain is anchored today.** The root keys exist on both sides:
`astra-registry/registry/v1/root.json` carries `"status": "provisioned"` and two
Ed25519 keys, and the daemon's `PRODUCTION_ROOT_KEYS` compiles in the same two.
`registry/v1/trust.json` is now signed by `astra-root-2026a` and delegates to an
index-signing key, `astra-index-2026a` — verified with the registry's own
`node tools/sign-trust.mjs --verify registry/v1/trust.json`, which also prints
the single reusable-workflow SHA the bot will accept in an attestation
(`e3329df252a46d747676cb540ae4b986af68a3ad`, the commit `plugin-release/v1`
points at). **The link still missing is the catalogue's own signature:**
`registry/v1/index.json` and `revocations.json` carry `"signatures": []`, so a
default Astra build has nothing to check and classifies every catalogue as
unsigned. Nothing here promises a guarantee that is not yet in place; see
[the security model](1-orientation/security.md) and
[`spec/registry-index.md` §0.1](spec/registry-index.md).

**None of it says the code is safe.** A plugin is a native process with your full
user privileges; there is no sandbox. A listing is not a safety review — nobody
reads your code, and the registry says so in its own policy.

---

## The other two ways a plugin reaches a machine

Both are for developers, both cost something, and **neither is publishing**:

- [Install a local `.astraplugin` file](5-publish/local-install.md) — a bundle
  that arrived out of band. Four permissions are refused outright, whatever the
  manifest asks for.
- [Sideload a source directory](5-publish/sideload.md) — the authoring loop.
  Requires Developer Mode, runs unsigned code with your full user account, and
  never auto-starts.

## See also

- [Install the CLI](install-cli.md) — where every command on this page comes from
- [Release with CI](5-publish/release-with-ci.md) — the workflow, in full
- [Get listed](5-publish/get-listed.md) — the submission and what follows it
- [Versioning](versioning.md) — what the numbers mean and how long a deprecation lasts
- [`spec/bundle-v2.md`](spec/bundle-v2.md) · [`spec/registry-index.md`](spec/registry-index.md)

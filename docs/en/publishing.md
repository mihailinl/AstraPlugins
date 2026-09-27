# Publishing a plugin

**One page, from an empty directory to a plugin users can install.** Every
command is here in order, with the output it produces. If you read exactly one
page about publishing, read this one; the deeper pages are linked where they
matter and none of them is required to finish.

---

## Read this part even if you read nothing else

Publishing a plugin to Astra means **one specific thing**: you tag a release in
your own GitHub repository, GitHub's CI builds the bundle and attests it, and
you submit it once, in the panel — once, ever.

These are **not** publishing, and each of them has been tried:

| Not publishing | Why it cannot work |
|---|---|
| Pushing your source to GitHub | The registry never reads your source tree. It reads a `.astraplugin` file attached to a release, and there isn't one |
| Sending someone a `.zip`, or a bundle you built on your laptop | The bytes carry no build attestation, so the registry refuses them however good the plugin is |
| Asking a maintainer to build it for you | Nobody builds your plugin but your repository's own CI. There is no other builder |
| Describing your plugin to the registry anywhere but the panel's submission page | The registry acts on a submission made in the panel, signed in, for a repository bound to your account. There is no other door. See [Submit](#8--submit-once-ever) |

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
first. There are prebuilt binaries now — download an archive for Linux or
Windows, check it against `SHA256SUMS.txt`, and no toolchain is involved.
Building from source still works and is the path on macOS and ARM Linux.
`cargo install astra-plugin-cli` is not a path at all; that page says why.

> **Do not read your build's health off the version number.** A CLI built before
> commit `5b8ab22` writes a release workflow GitHub rejects the moment you push
> your first tag. That fix landed on `master` *before* the bump to `0.2.1`, so a
> build can carry it and still print `0.2.0`, and no `0.2.1` lacks it. Installing
> from `master` today gets the fix whatever the number says. The check that
> actually settles it is the SHA `init-ci` prints, and this page runs it in
> [step 3](#3--set-up-the-release-workflow).

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

<!-- doctest: output from="astra-plugin new dice-roller" unrun="creates a directory tree; re-run it in an empty directory of your own" -->
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

<!-- doctest: output from="astra-plugin test ." unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
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

<!-- doctest: output from="astra-plugin init-ci" unrun="writes .github/workflows/release.yml into the working directory; re-run it in your own plugin" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned c3f342469d186ef48458992930bf1b7c583c78d4 (plugin-release/v1)
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

**Check the SHA it printed before you go on.** It must be the commit
`plugin-release/v1` points at today, and the only thing that can tell you what
that is, is the remote: `git ls-remote
https://github.com/mihailinl/AstraPlugins.git refs/tags/plugin-release/v1
'refs/tags/plugin-release/v1^{}'` — both refspecs, and the peeled `^{}` line
wins when the remote sends one, which is the pair `init-ci` itself asks for. If
your pin disagrees, re-run the `cargo install` line on
[Install the CLI](install-cli.md), then run `astra-plugin init-ci` again — it
rewrites the pin and keeps your inputs. Nothing is repaired in place, so an
existing `release.yml` keeps the stale SHA until you re-run it. The rest is
history, and dated: `plugin-release/v1` was an annotated tag from 2026-08-11 to
2026-08-19, a CLI older than commit `5b8ab22` pinned its tag object
`dc1a044876926e9cf1170f034e2eab533ec07641` where GitHub needs a commit, and
that is the bug that broke a real author's first release with `invalid value
workflow reference` before any job started; the tag is lightweight today, so no
build reports that SHA any more.

Detail, including what the generated file contains and why each of its three
permissions is required: [Release with CI](5-publish/release-with-ci.md).

<!-- doctest: cli -->
```bash
astra-plugin check --strict
```

<!-- doctest: output from="astra-plugin check --strict" unrun="needs a plugin project in the working directory; re-run it in your own plugin" -->
```
Checking plugin at ....
  NOTE: Missing plugin.author
  NOTE: Pin freshness not checked (pass --resolve-pin, or set ASTRA_PLUGIN_WORKFLOW_SHA)
  REGISTRY WARN: B_UNBOUND predicted once this listing needs a binding: there is no .well-known/astra-plugin-owner at the repository root (working tree). From the registry's cutover every first listing needs one, and every listing after the binding deadline; a release without it is refused B_UNBOUND. Mint a token in the panel and run `astra-plugin init-ci --binding <token>` — https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/5-publish/get-listed.md#bind-your-repository
  NOT CHECKED: B_BINDING_UNUSABLE, B_OWNER_CHANGED, B_REPOSITORY_RECYCLED, E_WORKFLOW_NOT_ALLOWED — only the registry can answer these, from the plugins service, GitHub and trust.json
  sections: [plugin], [entry], [capabilities]
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
```

`--fix` applies whatever can be fixed mechanically. `--resolve-pin` asks GitHub
whether your workflow pin is still the current one; it is off by default so that
neither `dev` nor CI needs the network to run a check.

## 4 · Push it, public — with the ownership file

<!-- doctest: cli -->
```bash
git init && git add -A && git commit -m "dice-roller 0.1.0"
git remote add origin https://github.com/you/dice-roller
git push -u origin main
astra-plugin init-ci --binding <token>
git add .well-known && git commit -m "Bind this repository to my Minice account" && git push
astra-plugin check --strict
```

Nothing about the first three lines is special — it is an ordinary repository.
But note what it is *not*: pushing this is not publishing the plugin, and
stopping here is where the two real submissions that prompted this page went
wrong. What makes it a published plugin is the tag in the next step.

**The binding line is the ownership proof, and it is not optional.** Between the
push and `init-ci`, sign in at https://astra.minice.ai/plugins with the Minice
account that will publish, and mint a binding token for `you/dice-roller` — the
panel looks the repository up on GitHub, which is why it has to be pushed
first. `init-ci --binding` writes the token as the first line of
`.well-known/astra-plugin-owner` at the root of your repository; committed on
your default branch, it is how the registry knows which account speaks for this
repository, which is the one thing the build attestation cannot say. Leave it
out and your first submission is refused `B_UNBOUND`.

Once you have tagged in the next step, `astra-plugin check --tag v0.1.0` reads
the line back from the tag's commit, as the registry will. The token is public
and authenticates no release, so never merge a binding line you did not mint
yourself. What it records, how long it lasts, and what a rename does to it are
in [Get listed — Bind your repository](5-publish/get-listed.md#bind-your-repository).

## 5 · Tag — this is the release

<!-- doctest: cli -->
```bash
astra-plugin version 0.1.0
git commit -am "release 0.1.0"
git tag v0.1.0
git push && git push --tags
```

<!-- doctest: output from="astra-plugin version 0.2.0" unrun="rewrites every manifest in a plugin project; re-run it in your own plugin" -->
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
[Release with CI §3](5-publish/release-with-ci.md#3--what-ci-does).

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

<!-- doctest: output from="astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin" unrun="needs that exact bundle, which is a build artefact and is not committed anywhere" -->
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

<!-- doctest: output from="astra-plugin publish . --dry-run --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
── only the registry can check these ────────────────────────
  · the build attestation, and that it was produced by the pinned Astra release workflow (a hand-built bundle is refused however good it is)
  · that the attestation's workflow commit is one the registry's trust.json allows (E_WORKFLOW_NOT_ALLOWED)
  · that the release assets are served from your repository's own release namespace
  · the binding verdict: that the token on the binding line at the tagged commit is bound to a Minice account (B_BINDING_UNUSABLE)
  · eligibility: that the account behind the token may publish (B_ACCOUNT_INELIGIBLE)
  · the ids against the identity record: that the repository and its owner are the ones this listing is recorded under (B_OWNER_CHANGED, B_REPOSITORY_RECYCLED)
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan

  All of them are described in the registry's docs/BOT-CHECKS.md, with the exact code
  each failure produces. What happens to a release that passes — published now,
  delayed 24 hours, or held for a person — is docs/POLICY.md.
```

Of that list, the binding verdict is the one your own work decides, and you did
it in [step 4](#4--push-it-public--with-the-ownership-file). The rest follow
from having tagged a release the workflow built.

## 8 · Submit, once ever

**Before you run this**, read the binding line back from your tag, exactly as
the registry will. It is the one check on this page you can fail while having
done everything else correctly:

<!-- doctest: cli -->
```bash
astra-plugin check --tag v0.1.0
astra-plugin publish
```

`publish` opens the panel's **submission page** in your browser, with the
repository and the tag filled in. It uploads nothing and holds no credential —
there is no `astra-plugin login`, no token in your shell history, no keyring to
integrate with. The page submits nothing until you do, signed in to the Minice
account your repository is bound to. `--print-url` prints the link instead of
opening a browser:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project in a bound git repository; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — submission for you/dice-roller@v0.1.0, in the panel

  Bound: `astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd` is line 1 of the owner file at HEAD. Submit in the
  panel signed in to the Minice account that minted that token. The page fills itself
  in from this link and submits nothing until you do. The registry reads the tag's
  commit, not HEAD — `astra-plugin check --tag v0.1.0` reads it the same way.

https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0
```

The submission carries **two facts**: your source repository (`you/dice-roller`)
and the release tag (`v0.1.0`). Everything else is read out of the attested
bundle, because everything in the bundle is covered by the attestation and is
therefore worth strictly more than anything typed into a form.

## 9 · What happens next

Detail, including every code: [Get listed §what happens after you
submit](5-publish/get-listed.md#3--what-happens-after-you-submit). The short
version: the panel shows the submission's state, and the same moments reach
you as notices — at your Minice account's verified e-mail address and in the
panel, and by Telegram only if you have linked it.

| Outcome | Means | Who is involved |
|---|---|---|
| **Published** | Committed, then in the signed catalogue | nobody |
| **Delayed** | Everything passed; it publishes itself at the time the panel shows | nobody |
| **Held** | A decision the registry is not entitled to make automatically | a moderator, in the panel |
| **Refused** | A check failed | you: fix it, then Recheck in the panel or tag again, as the code says |

**A first listing is always held for a person** — one of exactly three events
that need one, along with a newly requested high-risk permission and a change of
repository or binding. A moderator approves or rejects it in the panel; you do
nothing while you wait. No approval shortens a delay, and the registry's
`docs/POLICY.md` publishes the rules.

## 10 · Every release after that

Nothing. Tag, and CI does the rest; the registry detects the new tag of a
listed plugin by itself, and the panel shows its state.

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

There is nothing to submit and nothing to ping. A release that has not appeared
is on the panel's page for your plugin, with its state and the reason.

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
the reusable-workflow SHAs the bot will accept in an attestation — two of them
since the tag moved on 2026-08-19: the commit `plugin-release/v1` points at, and
the one it pointed at before. Since 2026-09-20 the catalogue clients are served
is signed with that key; the copies committed on the registry's `main`,
`registry/v1/index.json` and `revocations.json`, carry `"signatures": []` by
design, and no client reads them. **The link still missing is a signed
withdrawal list on Pages**, so revocation is not enforced yet. Nothing here
promises a guarantee that is not yet in place; see
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

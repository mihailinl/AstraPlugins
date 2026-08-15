# Release with CI

**A tag is the whole release process.** One command sets it up, and after that
you never hand-build a bundle again.

Everything on this page starts from the `astra-plugin` binary. If you do not
have it, [install the CLI](../install-cli.md) first — download a prebuilt
archive, or build from source if you want to. For the whole journey in
one page rather than this one tier of it, see
[Publishing a plugin](../publishing.md).

## Why not just `astra-plugin build` and upload it?

Because nothing vouches for a file you built on your laptop. The registry reads
GitHub's **build attestation** — a Sigstore keyless signature, minted from the
workflow's OIDC identity — which says *these exact bytes came from that workflow,
at that commit, in that repository*. A hand-built bundle carries no such thing
and is refused however good it is — with `E_ATTESTATION_MISSING`, by name.

For the same reason, **pushing your source to GitHub is not releasing** and
neither is sending someone the `.astraplugin` you built locally. The registry
never reads your source tree; it reads the assets on a tagged release, and it
pins them by digest.

You do not need, and are not asked for, a signing key. See
[the security model](../1-orientation/security.md).

## 1 · Write the workflow

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

<!-- doctest: output from="astra-plugin init-ci" unrun="writes .github/workflows/release.yml into the working directory; re-run it in your own plugin" -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned e3329df252a46d747676cb540ae4b986af68a3ad (plugin-release/v1)
    with   plugin-dir: .
           tag-prefix: v

  Next: commit this file, then release with
    astra-plugin version <semver>
```

**This works today, and each half of that is checkable.**
`.github/workflows/plugin-release.yml` is on `mihailinl/AstraPlugins`'s default
branch — `git ls-tree -r master --name-only .github/workflows` lists it — and
the released tag exists: `git ls-remote --tags origin` resolves
`plugin-release/v1` to `e3329df252a46d747676cb540ae4b986af68a3ad`. Because the
tag exists, `init-ci` pins that commit rather than a moving branch head, and it
no longer prints the "Not verified" caveat earlier versions of this page quoted.

That SHA is the same one the registry's root-signed `trust.json` allows in a
build attestation — `node tools/sign-trust.mjs --verify registry/v1/trust.json`
in `astra-registry` prints it under *reusable-workflow SHAs it allows*. A build
produced by any other workflow is refused at ingest with
`E_WORKFLOW_NOT_ALLOWED`, so the pin is not a nicety; it is what makes your
attestation mean something the registry can act on.

Re-run `init-ci` whenever a newer `plugin-release/vN` is published; it keeps
your inputs and only moves the pin.

That is the entire author-side CI. It is short because it delegates:

<!-- doctest: illustrative reason="the file `astra-plugin init-ci` writes; it lives in the author's repository, not in this one, and its pin is resolved at generation time" -->
```yaml
name: Release

on:
  push:
    tags: ["v*"]

# Required, and required HERE: a reusable workflow can only reduce the
# permissions its caller granted, never grant itself more. Leave all three.
permissions:
  contents: write       # create the Release and upload assets
  id-token: write       # mint the OIDC token that makes signing keyless
  attestations: write   # store the build attestation on GitHub

jobs:
  release:
    # Pinned by commit SHA, not by a moving tag: whoever can move
    # `plugin-release/v1` in mihailinl/AstraPlugins would otherwise own the build
    # step of every plugin that trusts it — and that build step runs in YOUR
    # repository with the token above. `astra-plugin init-ci` keeps this current.
    uses: mihailinl/AstraPlugins/.github/workflows/plugin-release.yml@e3329df252a46d747676cb540ae4b986af68a3ad  # plugin-release/v1
    with:
      plugin-dir: .
      tag-prefix: "v"
      linux-packages: ""      # e.g. "libasound2-dev pkg-config" for audio plugins
    # No `secrets: inherit`, deliberately. This workflow declares no secrets,
    # so the job that runs your build.rs and your npm lifecycle scripts has
    # nothing to leak.
```

Re-run `init-ci` to move the pin forward; it keeps the inputs you set.
`--offline` keeps the pin already in the file, and `--ref <sha-or-ref>` pins
something specific.

## 2 · Tag

<!-- doctest: cli -->
```bash
astra-plugin version 0.2.0
git commit -am "release 0.2.0"
git tag v0.2.0 && git push --tags
```

`astra-plugin version` rewrites `plugin.toml` **and** every other manifest in
the project in one edit — `Cargo.toml`, `package.json`, `pyproject.toml` — so
they cannot disagree. It refuses a version that sorts below the current one
unless you pass `--allow-downgrade`, because Astra refuses to install a
downgrade and such a release would be uninstallable.

The tag must match `tag-prefix` plus the manifest version, and CI asserts it
before it builds anything. `astra-plugin version` prints the exact tag to use:

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

## 3 · What CI does

This section describes `.github/workflows/plugin-release.yml` as it is written
in this repository, on `master`, at the commit `plugin-release/v1` points at —
which is the commit your `release.yml` calls.

Three jobs, and the split is the security property.

| Job | Runs your code | Holds a write token | What it does |
|---|---|---|---|
| **plan** | **no** | yes | Reads `plugin.toml` with Python's `tomllib` as *data*, checks tag == version, decides the build matrix, creates the draft Release |
| **build** (matrix) | yes | **no** | `astra-plugin check --strict`, `astra-plugin build`, verify, unpack, assert the glibc floor and the TypeScript bundle's self-containment |
| **publish** | no | yes | Re-derives every digest itself, writes `SHA256SUMS.txt`, attests, uploads, un-drafts the Release |

`plan` never executes anything out of the repository — no submodules, no
credentials persisted in `.git/config`. `build` runs your `build.rs` and your
lifecycle scripts and has no token to steal. `publish` downloads the artifacts,
hashes them itself, and attests what it hashed.

The matrix is decided from your plugin's language: `linux-x64` +
`windows-x64` for Rust, a single `noarch` leg for TypeScript and Python.

### What lands on the Release

| Asset | |
|---|---|
| `<id>-<version>-linux-x64.astraplugin` | one per platform key |
| `<id>-<version>-windows-x64.astraplugin` | |
| `<id>-<version>.sigstore.jsonl` | the attestation bundle, so a user with no network to GitHub can still check |
| `SHA256SUMS.txt` | the same digests the registry records |

The Release becomes visible only once every asset is attached.

### Attestation needs a public repository

Build attestations are published to a public transparency log; on a private
repository they require GitHub Enterprise. The workflow resolves your
repository's visibility and, when it is not public, says so in the job summary
and produces **unattested** bundles — which the registry will not list. That is
a real constraint, and it fails loudly rather than producing a release that
looks fine.

### Reproducibility

`astra-plugin build --reproducible` asserts deterministic packing: sorted
entries, a fixed mtime, a fixed compression level. Two builds from the same
inputs produce the same sha256. CI runs a reproducibility canary on every
release, which is what makes a third party's re-build meaningful.

## 4 · Check it yourself

Anyone can verify a release without trusting Astra or the registry:

<!-- doctest: cli -->
```bash
gh attestation verify dice-roller-0.2.0-linux-x64.astraplugin --repo you/dice-roller
astra-plugin verify dice-roller-0.2.0-linux-x64.astraplugin
```

`astra-plugin verify` reads the bundle itself and prints what it found:

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

Exit codes matter here and every release workflow branches on them: **1** means
the bundle is wrong, **2** means the CLI could not answer — a missing file, for
instance. The archive format, and what a verifier must reject, is
[`spec/bundle-v2.md`](../spec/bundle-v2.md).

## 5 · Then get listed

Once. → [Get listed](get-listed.md).

## Things that go wrong

| Symptom | Cause |
|---|---|
| The workflow never starts | `on: push: tags:` and `tag-prefix:` disagree. A glob narrower than the prefix never fires |
| "tag does not match the manifest version" | Run `astra-plugin version <v>` and commit before tagging |
| The Linux build fails on a missing header | Set `linux-packages: "libasound2-dev pkg-config"` in the caller workflow |
| The bundle is unattested | The repository is private |
| `MODULE_NOT_FOUND` at first launch | A TypeScript dependency the bundler could not follow. CI asserts against this; check the bundler's externals |
| A glibc error on a user's machine | Something in the archive needs a symbol above `GLIBC_2.39`. CI asserts this too |
| `invalid value workflow reference` before any job starts | The pin names a commit that does not carry `plugin-release.yml`. Re-run `astra-plugin init-ci` to repin to `plugin-release/v1` |
| The registry refuses the release with `E_WORKFLOW_NOT_ALLOWED` | The build did not run the pinned Astra reusable workflow. Re-run `init-ci`, retag, and let CI rebuild |

More: [troubleshooting](../6-operate/troubleshooting.md).

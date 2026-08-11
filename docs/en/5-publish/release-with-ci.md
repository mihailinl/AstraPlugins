# Release with CI

**A tag is the whole release process.** One command sets it up, and after that
you never hand-build a bundle again.

## Why not just `astra-plugin build` and upload it?

Because nothing vouches for a file you built on your laptop. The registry reads
GitHub's **build attestation** — a Sigstore keyless signature, minted from the
workflow's OIDC identity — which says *these exact bytes came from that workflow,
at that commit, in that repository*. A hand-built bundle carries no such thing
and is refused however good it is.

You do not need, and are not asked for, a signing key. See
[the security model](../1-orientation/security.md).

## 1 · Write the workflow

<!-- doctest: cli -->
```bash
astra-plugin init-ci
```

<!-- doctest: output from="astra-plugin init-ci ." -->
```
  Created:   .github/workflows/release.yml
    calls  mihailinl/AstraPlugins/.github/workflows/plugin-release.yml
    pinned 985ad7ebab49957cc4e000edd814a62605579ff0 (default branch)
    with   plugin-dir: .
           tag-prefix: v

  Note: 'plugin-release/v1' does not exist in mihailinl/AstraPlugins yet, so this pins the
  current head of its default branch. Re-run `astra-plugin init-ci` once the
  tag exists to move onto a released workflow.

  Not verified: whether .github/workflows/plugin-release.yml exists at that commit. If
  the tag push fails with 'invalid value workflow reference', it does not;
  pin one that does with `astra-plugin init-ci --ref <commit>`.

  Next: commit this file, then release with
    astra-plugin version <semver>
```

> **Releasing does not work yet, and this is the page that has to say so.**
> `plugin-release.yml` is not on `mihailinl/AstraPlugins`'s default branch. It
> exists only on the branch that carries this documentation, which has not been
> pushed — `git ls-remote origin` lists `master` and one feature branch, and
> neither tree contains the file. So the commit `init-ci` resolves is a real,
> immutable commit that **does not contain the workflow it names**, and a tag
> pushed today fails in GitHub Actions before any job starts:
>
> ```
> invalid value workflow reference: no version found for owner mihailinl
> repo AstraPlugins workflow .github/workflows/plugin-release.yml
> ```
>
> Nothing is built, nothing is attested, and no release assets appear — which
> means [get listed](get-listed.md) cannot be reached either, since its
> prerequisite is a release that CI built.
>
> This becomes true the moment this work lands on the default branch, or is
> tagged `plugin-release/v1`; re-run `init-ci` then and it will repin to a
> commit that has the file. Until then the only pin that runs is one you name
> yourself, at a commit you have checked carries it:
>
> ```bash
> astra-plugin init-ci --ref <40-hex commit containing plugin-release.yml>
> ```
>
> `init-ci` says "Not verified" about exactly this, and it cannot do better:
> it resolves the ref with `git ls-remote`, which answers with commits and
> knows nothing about the files in them
> (`astra-plugin-cli/src/commands/init_ci.rs`).

The note in the output above is about the pin's *provenance*, and is true
whenever you read it: with no `plugin-release/v1` tag, `init-ci` pins the
default branch's head commit instead. What the tag adds is a promise that the
thing it points at does not change shape. Re-run `init-ci` when the tag exists;
it keeps your inputs and only moves the pin.

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
    # Pinned by commit SHA, not by a moving tag: whoever can move a tag in
    # mihailinl/AstraPlugins would otherwise own the build step of every plugin
    # that trusts it — and that build step runs in YOUR repository with the
    # token above. `astra-plugin init-ci` keeps this line current.
    uses: mihailinl/AstraPlugins/.github/workflows/plugin-release.yml@985ad7eb…
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

The tag must match `tag-prefix` plus the manifest version, and CI asserts it.

## 3 · What CI does

This section describes `.github/workflows/plugin-release.yml` as it is written
in this repository. Read it with the note in §1 in hand: until that file is on
the default branch, this is what *will* happen, not what happens today.

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
  artifact sha256: d7dd70c5b2c4341af51a9ec29e63adc25f5a31d6b5d8f189c1d39e4f77780eb4
  manifest digest: 7d66d26977a939f849f998009eb48b12ac7c741b69338be1cc6247a5ed64df6c
  size:            2730385 bytes (2666.4 KB)
  legacy in-ZIP signature: absent

  3 listed files:
    0644        210  206e62245f5205c3  README.md
    0755    8727528  d8b2a8fa76e520bd  bin/dice_roller
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

More: [troubleshooting](../6-operate/troubleshooting.md).

# Publishing plugins

Everything you need to turn source into a distributable bundle that users can install from the Astra registry or sideload by hand.

## What establishes trust

Read this before the signing section, because the order surprises people:

**Local keys are not a trust signal in Astra.** `astra-plugin build` does not sign, and a signature made with a key you hold is checked against nothing on the user's machine. What makes Astra install a plugin is:

1. **A digest.** `sha256` of the whole `.astraplugin` file — one number, in three places: the GitHub attestation's subject, the registry's release record, and what the daemon hashes before it extracts a byte. A mismatch is a hard block with no override.
2. **A countersignature.** The registry's index key signs that digest together with the plugin id, version and platform. The daemon verifies it against index keys named in a root-signed `trust.json`.
3. **An attestation.** Your release is built by GitHub Actions with keyless (OIDC) signing, so the provenance names the repository, workflow and commit the bytes came from. The registry verifies it before listing; the daemon records what the registry asserted, and the provenance panel says plainly that it is an assertion, not a proof.
4. **A pin.** The first install of a plugin id records the author identity. An update whose identity differs is refused, with no override, ever.

None of those four involve a key you generate, store or rotate. Losing an author key is a non-event, because there is nothing built on top of it. That is deliberate: key custody is the step authors get wrong, and a plugin ecosystem that requires it gets a small one.

The first-party plugins Astra ships travel this exact path — the same index record, the same digest check, the same pin. Until the 3.10 migration they had a private door (a publisher key compiled into the daemon), and the effect was that the third-party path could have been broken indefinitely without anyone noticing. Now there is one path and everyone is on it.

## The `.astraplugin` bundle

`.astraplugin` is a **ZIP archive** with a specific layout. The daemon validates it, checks its digest against the record, extracts it into its plugin directory, and launches the `entry.command` with credentials.

```
<plugin-id>-<version>.astraplugin
├── plugin.toml                # Manifest
├── bin/                       # Compiled binary (Rust only)
│   └── my_plugin.exe
├── dist/                      # Bundled JS (TypeScript only)
│   └── index.js
├── src/                       # Python sources (Python only)
│   ├── plugin.py
│   └── __init__.py
├── requirements.txt           # Python deps (Python only)
├── requirements.lock          # Python deps resolved by uv (Python only)
├── ui/                        # Custom UI files (optional)
├── locales/                   # i18n JSON files (optional)
├── icon.png | icon.svg        # Optional branding
├── README.md                  # Optional
├── LICENSE                    # Optional
├── SIGNATURE                  # Legacy Ed25519 signature — retiring, see below
└── PUBKEY                     # Legacy Ed25519 public key — retiring, see below
```

When `astra-plugin build` produces an archive it:

1. Runs the language-specific build step.
2. Copies the compiled artefact into the expected directory.
3. Rewrites `entry.command` to point at the bundled path (Rust only — Python/TS paths inside the archive are stable).
4. Adds `ui/`, `locales/`, icon and docs if they exist next to `plugin.toml`.
5. Writes `MANIFEST.json` — every file, its `sha256`, size and mode.

`build` does **not** sign, whatever is in `~/.astra/plugin-keys/`. Two builds of the same source produce byte-identical archives on any machine, which is what makes `--reproducible` mean something a reviewer can check.

Its last line says so:

```
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
  See https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/publishing.md#what-establishes-trust
```

## Signing

You almost certainly do not need this section. Publishing works, end to end, without ever running `keygen` — see [What establishes trust](#what-establishes-trust).

### What a signature here is, and is not

`astra-plugin sign` appends the legacy in-ZIP `SIGNATURE`/`PUBKEY` pair. The daemon checks that pair against a **pinned Astra publisher key**, never against the `PUBKEY` inside the archive — because a `PUBKEY` an attacker can write is a `PUBKEY` an attacker can match. So a bundle signed with *your* key is untrusted by construction, exactly as an unsigned one is. It does not make Astra install anything, it does not raise a badge, and it does not change what a user sees.

Where it genuinely helps is narrower and worth stating precisely: an attacker who takes over your GitHub account can produce a *perfect* attestation — real OIDC, real workflow, real commit — and cannot produce a signature from a key that never touched your GitHub account. Publishing your public key somewhere users read gives them one thing to check that a stolen session cannot forge. That is defence in depth against one specific, realistic attack, and it is the only claim this feature supports.

### Generate a keypair

```bash
astra-plugin keygen
```

Output:

- `~/.astra/plugin-keys/private.key` — base64-encoded Ed25519 seed, written 0600 in a 0700 directory. **Keep secret.**
- `~/.astra/plugin-keys/public.key` — safe to publish.

Add `--force` to overwrite an existing keypair.

### Sign a built bundle

```bash
astra-plugin build --target linux-x64
astra-plugin sign my-plugin-0.2.0-linux-x64.astraplugin
```

Or with a key kept somewhere else — a path, never the key itself, since anything on a command line is visible in `ps` and lands in your shell history:

```bash
astra-plugin sign my-plugin-0.2.0-linux-x64.astraplugin --key /media/usb/author.key
```

`sign` verifies the bundle before it signs it, refuses a bundle that already carries the pair, and re-verifies afterwards. **Signing changes the file**, and therefore changes the `sha256` the registry countersigns — so sign before you upload, and publish the digest of the signed file.

Do not sign in CI. The release workflow's build job holds no secrets on purpose: it runs your `build.rs` and your npm lifecycle scripts, and a key in that job is a key any dependency can read.

### Retirement

The in-ZIP pair is going away. Its digest is `SHA256(name₀ ‖ content₀ ‖ name₁ ‖ content₁ ‖ …)` with no delimiters and no length prefixes, so entry `"ab"` with content `"c"` hashes identically to entry `"a"` with content `"bc"` — an ambiguity that `sha256` of the whole file does not have.

| Release | What changes |
| --- | --- |
| **astra-plugin 0.3.0 / Astra 0.2.0** (this one) | `build` stops signing; signing moves to `astra-plugin sign`. The daemon still reads the pair, so every bundle already published keeps installing. |
| **astra-plugin 0.4.0 / Astra 0.3.0** | No change. This is the window in which first-party plugins are republished through the registry, so that nothing first-party still depends on the pinned key. |
| **astra-plugin 0.5.0 / Astra 0.4.0** | `astra-plugin sign` is removed, the daemon stops reading the pair, and `SIGNATURE`/`PUBKEY` leave the format. A bundle installs entirely on its registry record. |

If you have never signed a bundle, none of this affects you.

## Distribution

### Direct download

Ship the `.astraplugin` file from your website, GitHub Releases, or any file host. Users download and drag the file into Astra's Plugins page.

### Git + release artefacts

Typical release workflow:

1. Bump `plugin.version` in `plugin.toml`.
2. Commit, tag (`git tag v0.2.0`), push.
3. `astra-plugin validate` → `astra-plugin build -o dist/plugin-0.2.0.astraplugin`.
4. Upload the `.astraplugin` to the GitHub Release for that tag.

CI-friendly because `astra-plugin` is a single binary.

### Registry

A central plugin registry is planned. Until it ships, share plugins via direct URLs.

## Sideloading

The daemon exposes two RPCs for installing a `.astraplugin`:

- `SideloadPlugin(bytes)` — accept the bundle over gRPC. Used by the Astra UI's file picker.
- `ImportPluginFile(path)` — instruct the daemon to read the file from disk. Used when a user drags the file into the UI.

Both validate the manifest, extract into `~/.astra/plugins/<id>/`, and launch the process. A bundle that arrived out of band has no registry record vouching for it, so it lands at a lower tier: promoted to a full install if its digest turns up in a fresh index, and otherwise gated behind Developer Mode with the high-risk permissions refused outright. Installing the same plugin from the Plugins page needs no setting changed at all — which is why the refusal message points there first.

Uninstalling a plugin stops the process, removes the extracted directory, and clears plugin state.

## Upgrade strategy

- Bump `plugin.version` for every release.
- The daemon stores installed plugin versions and surfaces an "Update available" badge when the new bundle has a higher SemVer.
- Breaking config changes? Add new fields with defaults rather than renaming existing ones — the daemon keeps old config across upgrades.

## Localisation

Ship a `locales/` directory inside your bundle:

```
locales/
├── en.json
├── ru.json
├── uk.json
├── de.json
├── es.json
├── zh-CN.json
└── ja.json
```

Each SDK has an `I18n` helper that reads these files and falls back gracefully on unknown keys. The manifest translates field labels (`ActionType.MyAction`, `FieldLabel.X`) — keep the IDs in your code stable and the display text in the JSON files.

## Checklist before releasing

- [ ] `astra-plugin validate` passes without errors.
- [ ] `astra-plugin build` succeeds and produces an archive of reasonable size.
- [ ] `plugin.toml` has `description`, `author`, and `license`.
- [ ] `[config]` schema, if present, has sensible defaults for every field.
- [ ] Test the bundle by sideloading into a clean daemon instance.
- [ ] `locales/` covers all strings your plugin shows to users.
- [ ] `README.md` documents what the plugin does and any runtime requirements.
- [ ] You have a way to reach users if you need to revoke a compromised release.

# Publishing plugins

Everything you need to turn source into a signed, distributable bundle that users can sideload into Astra.

## The `.astraplugin` bundle

`.astraplugin` is a **ZIP archive** with a specific layout. The daemon validates, (optionally) verifies the signature, extracts it into its plugin directory, and launches the `entry.command` with credentials.

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
├── SIGNATURE                  # Ed25519 signature (if bundle is signed)
└── PUBKEY                     # Ed25519 public key (if bundle is signed)
```

When `astra-plugin build` produces an archive it:

1. Runs the language-specific build step.
2. Copies the compiled artefact into the expected directory.
3. Rewrites `entry.command` to point at the bundled path (Rust only — Python/TS paths inside the archive are stable).
4. Adds `ui/`, `locales/`, icon and docs if they exist next to `plugin.toml`.
5. If `~/.astra/plugin-keys/private.key` exists, signs every entry with Ed25519 and adds `SIGNATURE` and `PUBKEY` to the archive.

## Signing

### Generate a keypair

```bash
astra-plugin keygen
```

Output:

- `~/.astra/plugin-keys/private.key` — base64-encoded Ed25519 seed. **Keep secret.** Anyone with this file can sign new versions of your plugin and users will trust them.
- `~/.astra/plugin-keys/public.key` — safe to publish.

Add `--force` to overwrite an existing keypair (useful for rotation — but invalidates trust relationships you've already established).

### Sign during build

There's no separate sign command: once a keypair exists, `astra-plugin build` signs automatically. The archive contains:

- `SIGNATURE` — a signed manifest of every other file in the archive.
- `PUBKEY` — the public key used. Users can match this against a known-good value (your website, your key pinning policy) before installing.

To publish an **unsigned** build, either delete the private key or build on a machine that doesn't have it.

### Verifying signatures

Signature verification happens on the daemon side when sideloading. The daemon exposes the bundle's `PUBKEY` in the Plugins UI so users can compare fingerprints before clicking "Install".

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

Both verify the signature (if present), validate the manifest, extract into `~/.astra/plugins/<id>/`, and launch the process.

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
- [ ] `PUBKEY` fingerprint is documented somewhere users can verify it.
- [ ] `locales/` covers all strings your plugin shows to users.
- [ ] `README.md` documents what the plugin does and any runtime requirements.
- [ ] You have a way to reach users if you need to revoke a compromised release.

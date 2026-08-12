# Get listed

**A plugin is listed once, ever.** After that, releases are zero-touch: tag, let
CI build and attest, and the registry picks it up.

Prerequisite: [a release built by CI](release-with-ci.md), on a **public**
repository, with the `.astraplugin` assets attached and attested.

**That prerequisite cannot be met today.** The reusable workflow `init-ci`
points your repository at is not on `mihailinl/AstraPlugins`'s default branch,
so a tag push fails before any job runs and no release assets are produced —
[the note in §1 of "Release with CI"](release-with-ci.md#1-write-the-workflow)
has the detail and the workaround. Everything below is the shape of the process
and is worth reading now; submitting a listing for a release that does not exist
is not.

## 1 · Preflight

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

It runs every check the registry runs that can be run locally, and then — the
half that matters — **names the ones only the registry can run**, so you know
what is still unproven:

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
```

### What your listing will look like

Two files decide that, and both are ones you already have next to
`plugin.toml`. Neither is named anywhere in the manifest — the packer picks them
up because of what they are called, and the registry reads them back out of the
bundle it has just verified. You never type a URL, and nobody can type one for
you.

**The icon** — the picture on your plugin's card. Any one of:

<!-- doctest: illustrative reason="the accepted filenames, not a command; spec/icon-formats.yaml is the list both the packer and the registry read" -->
```
icon.png    icon.webp    icon.svg    icon.jpg    icon.ico
```

`astra-plugin new` scaffolds a placeholder `icon.svg` so there is something to
replace. Draw it square; it is shown at roughly 64 pixels, so it wants a bold
silhouette rather than fine detail, and it should read on both a light and a
dark background because the store follows the user's theme. PNG with a
transparent background is the usual answer.

If you ship an SVG, keep it static: no `<script>`, no `on*` handlers, no
`<foreignObject>`, and no reference to anything off your machine. An icon
carrying any of those is dropped and your plugin lists without a picture. It
does not fail your release — a decorative file is not a gate on shipping
software — but you get a warning saying so, and nobody sees your icon.

**`README.md`** — your plugin's page, shown when somebody clicks the card. It is
what a person reads while deciding whether to install you, which makes it worth
more than the one-line summary.

It renders as GitHub-flavoured markdown, including tables. Screenshots work, and
a paragraph made only of images becomes a gallery row:

<!-- doctest: illustrative reason="markdown an author writes in their own README; there is nothing here for a runner to execute" -->
```markdown
![The command editor, mid-roll](docs/editor.png)
![The trigger firing on a natural 20](docs/trigger.png)
```

Three rules, all of which the registry applies when it derives your listing:

- **Link images with a relative path**, and commit them to your repository. They
  are rewritten to point at the exact commit your release was built from, so a
  picture cannot change after somebody approved the listing.
- **Images hosted anywhere but GitHub are dropped** and replaced by their alt
  text. Build badges included. This is a privacy rule rather than a security
  one: every remote image in a rendered README is a request from a user's
  machine, made before they have installed anything.
- **Raw HTML is stripped.** Use markdown for layout.

Long READMEs are truncated at 16 KB on a line boundary, with a link to the rest
on GitHub.

## 2 · Submit

<!-- doctest: cli -->
```bash
astra-plugin publish
astra-plugin publish --print-url
```

It opens a prefilled issue on the registry in your browser. **It uploads
nothing and holds no credential** — there is no `astra-plugin login`, no token
in your shell history, no keyring to integrate with.

The submission carries **two facts**:

| Field | Why it is typed rather than read |
|---|---|
| Source repository (`you/dice-roller`) | The bundle cannot vouch for where it is served from |
| Release tag (`v0.2.0`) | Same |

Plus two confirmations: that you own or maintain the repository, and that you
have read the policy.

**Everything else is read out of the attested bundle** — the id, the version,
the display name, the summary, the licence, the capabilities, the permissions,
the platforms, the digests, the sizes. That is not a convenience: everything in
the bundle is covered by the attestation, which makes it strictly more
trustworthy than anything typed into a form. It also deletes a whole class of
rejection, because there is no form for `plugin.toml` to disagree with.

## 3 · What happens next

Four outcomes:

| Outcome | Means | Who is involved |
|---|---|---|
| **Published** | Committed, and in the catalogue on the next index build | nobody |
| **Delayed** | Everything passed; it publishes itself at a stated time | nobody |
| **Held** | A decision the registry is not entitled to make automatically | a maintainer, within 48 h |
| **Refused** | A check failed | you: fix it and comment `/recheck` |

A release publishes itself with no human when all of these hold: it comes from
the repository already listed for that plugin, every bot check is green, the
version is strictly newer, it asks for no high-risk permission it did not
already have, and it asks for no new permission or capability at all. Drop only
the last and it still self-publishes, after a delay.

### The three things that need a person

Exactly three, and the list does not grow without a change to the registry's
published policy:

| Event | Why |
|---|---|
| **The first listing of a plugin** | Once, ever. Nothing is pinned yet, so nothing later can be checked against it |
| **A newly requested high-risk permission** | The user will be asked to consent to it; somebody should have read what it is for first |
| **The repository or identity changed** | Every installed copy carries a pin to the old repository. A repository change is an author change until somebody says otherwise |

High-risk here is four names: `client`, `dom_access`, `send_chat_message`,
`set_theme_contribution` — matched in `[capabilities]` and `[permissions]`
alike, because the section you declare them in is not the point. `push_to_ui`
gets a consent checkbox but not a review: it draws inside a panel your plugin
already owns.

**The SLA is 48 hours** for those, from the moment the bot comments. There is
one maintainer, which is precisely why the list is three items long.

## 4 · Every release after that

Nothing. Tag, and CI does the rest; the registry notices the release and
regenerates the index.

If it has not noticed:

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

That is the manual ping for a plugin that is **already listed**. Without it,
`publish` opens a first-listing request.

## What a listing does not mean

A listing is not a safety review. Nobody reads your code, and the registry says
so in its own policy: a permission decides what the daemon will do *for* a
plugin and nothing about what the plugin's process may do to the machine. There
is no sandbox. See [the security model](../1-orientation/security.md).

## The state of this today

One thing a reader deserves to know before following this page.

**The signing chain is not anchored.** The root keys exist — `root.json` carries
`"status": "provisioned"` and the daemon compiles in the same two — but a root
key does not sign a catalogue. It signs `trust.json`, which delegates to an
index-signing key, and no `trust.json` has been signed yet. With nothing
delegated, every catalogue classifies as unsigned and the bot stops each ingest
at `E_TRUST_UNPROVISIONED`. See
[`spec/registry-index.md` §0.1](../spec/registry-index.md).

The repository itself is live at
[`mihailinl/astra-registry`](https://github.com/mihailinl/astra-registry), so
the submission path on this page works today: your issue is read, the checks run
and the bot answers. What is still pending is the last link of the chain that
lets Astra *install* from what it publishes.

Nothing on this page changes when that lands — a signed `trust.json` appears and
the index it delegates to starts carrying a signature.

## See also

- [`spec/registry-index.md`](../spec/registry-index.md) — the index, revocations, and the verification algorithm
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — what the bot reads out of your archive
- [Versioning](../versioning.md) — what the numbers mean and how long a deprecation lasts

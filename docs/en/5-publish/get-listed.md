# Get listed

**A plugin is listed once, ever.** After that, releases are zero-touch: tag, let
CI build and attest, and the registry picks it up.

Prerequisite: [a release built by CI](release-with-ci.md), on a **public**
repository, with the `.astraplugin` assets attached and attested. That
prerequisite is met by tagging — the reusable workflow is on
`mihailinl/AstraPlugins`'s default branch and released as `plugin-release/v1`,
so a tag push builds and attests. Everything on this page assumes you have done
that; if you have not, do [Release with CI](release-with-ci.md) first, or read
[Publishing a plugin](../publishing.md), which is the whole journey in one page.

**What does not substitute for it**, because each of these has been tried: a
repository containing your source, a `.zip` sent to somebody, a bundle you built
on your laptop, or a message asking a maintainer to build it. The registry lists
release assets that CI attested, and nothing else.

Every step below is `astra-plugin`, a commit in your own repository, or the
panel at https://astra.minice.ai/plugins, signed in to your Minice account. If
you do not have the CLI, [install the CLI](../install-cli.md) first — there are
prebuilt binaries.

## 1 · Preflight

<!-- doctest: cli -->
```bash
astra-plugin publish --dry-run
```

It runs every check the registry runs that can be run locally, and then — the
half that matters — **names the ones only the registry can run**, so you know
what is still unproven:

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
```

**One of those you settle in advance, and must.** The binding verdict reads the
line [Bind your repository](#bind-your-repository) writes. Commit it before you
tag and the check has something to find; leave it out and the first answer is
`B_UNBOUND`.

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

**Keep it under 8 KiB** (8,192 bytes). Every listing's icon is inlined into one
signed catalogue that every Astra install downloads whole, so a big icon is
paid for by every user of every plugin. A larger one is dropped the same way —
your release is listed, with a letter on its card instead of your picture — and
`astra-plugin build` warns you before you tag. Export it at 128×128: as WebP at
quality 80 that is a few kilobytes even for detailed art, and a flat design is
usually smaller still as an SVG.

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

## Bind your repository

**A listing belongs to a Minice account.** Every first listing, and every
release of a listing that has one, is read against a **binding**: one line in
`.well-known/astra-plugin-owner` at the root of your repository, written by the
CLI from a token you mint in the panel, signed in to the Minice account that
will publish. It is the one step on this page that is not a command, and
skipping it is the most common way a correct, honest first submission is
refused.

**1 · Mint a token.** Sign in at https://astra.minice.ai/plugins with the Minice
account that will own the listing — it needs `astraUser`, which comes with
owning Astra — and mint a binding token for this repository.

**2 · Write the line.** Anywhere inside the repository:

<!-- doctest: cli -->
```bash
astra-plugin init-ci --binding <token>
```

It writes `astra-binding: <token>` as the **first line** of
`.well-known/astra-plugin-owner` at the repository root, removes any earlier
binding line in any spelling, keeps your login lines, and uses no network:

<!-- doctest: output from="astra-plugin init-ci --binding k3Vq9ZtW2xLr8NfBcY5pHd" unrun="rewrites .well-known/astra-plugin-owner in a git repository; re-run it at the root of your own" -->
```
  Rewrote: .well-known/astra-plugin-owner
    line 1   astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd
    kept     1 other line(s), byte for byte

  This token is public once you push it. It records one Minice account's consent
  to publish from this repository, and it authenticates no release: never merge a
  binding line you did not mint yourself. What that means, and what a rename or a
  transfer does to it:
    https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/5-publish/get-listed.md#bind-your-repository

  Next: commit this file on your default branch, then tag. Before you push the tag,
    astra-plugin check --tag <tag>
  reads the line back from the tagged commit, as the registry will.
```

**3 · Commit it on your default branch, then tag.** Before you push the tag,
read the line back exactly as the registry will — from the tag's commit, not
from your working tree:

<!-- doctest: cli -->
```bash
astra-plugin check --tag v0.1.0
```

A malformed line fails here, with `B_BINDING_MALFORMED`, while it is still
free to fix. A missing one is a warning predicting `B_UNBOUND`. Four answers
only the registry can give are named as not checked, every time.
**4 · Submit in the panel.** `astra-plugin publish`
opens the panel's submission page with the repository and the tag filled in,
for example
https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0 —
the page submits nothing until you do, signed in.

**What the token is, and is not.** A binding token is **public**: it sits in a
file in a public repository. It records **one account's consent** to publish
from this repository, and it **authenticates no release** — a release that
nothing holds publishes before the account is told. So **never merge a binding
line you did not mint yourself**: a pull request that adds or changes one is
asking you to hand your listing to somebody else's account.

**Where the line must be.** At the root of the repository, whatever directory
your plugin is in; in the commit your release tag points at; and within the
first 4096 bytes of the file. One line covers every plugin in the repository.
Deleting it from the default branch later ends nothing that is already bound.

**How long a minted token lasts.** A minted token expires 30 days after its mint
unless a live submission names it or its line is on the repository's default
branch when the rule is applied — the rule is re-tested before each expiry
decision. So an author who tags much later without the line on the default
branch mints again, and one whose line is still on that branch when the rule is
applied does not. A line committed and later removed does not keep a token
alive.

**Signing in.** The registry reads the account's eligibility from its last
verified sign-in, which counts for 12 hours. A release of a bound repository
waits while the account has not signed in within that time; the panel says so,
and a `notice.sign_in` notice asks you to sign in. Nothing publishes until you
do.

**Where notices go.** To the Minice account's verified e-mail address, and to
the panel. Telegram is an optional extra channel you may link; nothing requires
it.

**A rename or a transfer strands installed copies.** Astra identifies an
installed plugin by its repository, `github:owner/name`. Rename the repository
or transfer it to another owner and every installed copy stops receiving
updates until it is reinstalled from the new name. Nothing overrides this.

**For a plugin that is already listed.** An unbound listing is
`grandfathered`: it keeps publishing as it does today until the later of the
binding deadline and the registry's cutover. The deadline is fixed before
third-party bindings open, and published by the registry. After it, an unbound
listing is `frozen`: installed copies keep working and it stays installable,
but no new release of it is published until one carrying a binding line is — a
bound release unfreezes it, with no penalty. The first release carrying a
binding line is held once, until a moderator approves it, `R_FIRST_BINDING`. And
from the cutover, a release of a `grandfathered` listing that was held and
approved waits until the listing is bound.

**Preflight.** `astra-plugin check` refuses an id the registry refuses — a
reserved id, or one outside the registry's id pattern — and a malformed binding
line. `astra-plugin dev` and `astra-plugin build` refuse neither: the registry's
rules decide what gets listed, never what you may run.

## 2 · Submit in the panel

<!-- doctest: cli -->
```bash
astra-plugin publish
astra-plugin publish --print-url
```

It opens the panel's **submission page** in your browser, with your repository
and tag filled in. **It uploads nothing and holds no credential** — there is no
`astra-plugin login`, no token in your shell history, no keyring to integrate
with. The page fills itself in from the link and submits nothing: you submit it,
signed in to the Minice account your repository is bound to. `--print-url`
prints the link instead:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project in a bound git repository; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — submission for you/dice-roller@v0.1.0, in the panel

  Bound: `astra-binding: k3Vq9ZtW2xLr8NfBcY5pHd` is line 1 of the owner file at HEAD. Submit in the
  panel signed in to the Minice account that minted that token. The page fills itself
  in from this link and submits nothing until you do. The registry reads the tag's
  commit, not HEAD — `astra-plugin check --tag v0.1.0` reads it the same way.

https://astra.minice.ai/plugins/_/submit?repo=you/dice-roller&tag=v0.1.0
```

A repository with no binding line is told so above the link, and where to read
how to bind; a checkout without the tag gets one line saying the tag has to be
pushed. Both are reminders, not errors: the registry reads the tag's commit and
the release from GitHub, so what matters is what you pushed.

The submission carries **two facts**:

| Field | Why it is typed rather than read |
|---|---|
| Source repository (`you/dice-roller`) | The bundle cannot vouch for where it is served from |
| Release tag (`v0.1.0`) | Same |

**Everything else is read out of the attested bundle** — the id, the version,
the display name, the summary, the licence, the capabilities, the permissions,
the platforms, the digests, the sizes. That is not a convenience: everything in
the bundle is covered by the attestation, which makes it strictly more
trustworthy than anything typed into a form. It also deletes a whole class of
rejection, because there is no form for `plugin.toml` to disagree with.

## 3 · What happens after you submit

The panel shows your submission's state and every reason attached to it, and
the same moments reach you as notices: at the Minice account's verified e-mail
address and in the panel, and by Telegram only if you have linked it — nothing
requires Telegram. The rules below are the registry's, published in its
`docs/POLICY.md`; the codes are the ones the panel shows, with English titles at
launch.

### The states a submission moves through

| State | Means |
|---|---|
| `received` | The panel accepted your submission and nothing has read it yet |
| `checking` | The registry's bot is reading the release and verifying every asset from scratch |
| `held` | Everything a machine can decide passed, and one decision is a person's — see below |
| `approved` | A moderator approved the hold; it publishes when nothing else is waiting |
| `delayed` | Everything passed; it publishes itself at the time the panel shows. Since the registry's contract 3.0.0, no release you submit waits here |
| `published` | Committed to the registry |
| `served` | In the signed catalogue that Astra installs from |
| `refused` | A check failed. The panel names the code, and whether a Recheck can clear it or it needs a new tag |
| `stopped` | You stopped it before it published, and it will not |

*Amended 2026-09-26 (registry contract 3.0.0).* Before this date, this page said
that a first listing is always held for a person. The registry's own rule is
`astra-registry/docs/POLICY.md` §2.1 and §3.

**A release that passes every automatic check is published at once**, a first
listing included. Nobody approves it, and there is no publication delay. The
registry's checks are the whole gate, and a failed one still refuses the
release.

**It is marked as not reviewed by Astra moderators.** Every version starts that
way. A moderator may read a version later and mark it reviewed. The mark
belongs to that one version, so your next release starts as not reviewed again.

**Users see a warning.** From the Astra release that adds the mark, Astra warns
before it installs a version that is not reviewed, including an install that
Astra's AI tools ask for. It also warns wherever a user starts an update to
such a version, and applies the update only once the user has acknowledged the
warning. The plugins panel shows the mark on your plugin's page. Astra 0.2.x,
and every Astra release before the one that adds the mark, shows no mark and no
warning.

**`reviewed` means that a moderator read that version, and nothing more.** It is
not a security review, a code audit, an endorsement or a sandbox. A later
advisory, yank or delist always wins over it.

A first listing, a newly requested high-risk permission, a wider permission set
and a name a check flags publish at once like any other release, and carry
`P_REVIEW_PRIORITY`, so that moderators read them first. High-risk here is four
names: `client`, `dom_access`, `send_chat_message`, `set_theme_contribution` —
matched in `[capabilities]` and `[permissions]` alike, because the section you
declare them in is not the point.

### When the answer is a code

A refusal is not a verdict on your plugin; it is a named, fixable condition, and
the panel says which of two ways it clears. **Recheck**, a button in the panel,
re-runs every check from scratch against the same tag — for a fix outside the
tagged bytes, such as a release asset you forgot to attach. **A new tag** is the
only way to change anything inside them, because the attestation covers those
exact bytes. The binding codes:

| Code | What it means | Fix |
|---|---|---|
| `B_UNBOUND` | No binding line at the tagged commit, and this listing needs one | Bind the repository and tag again: [Bind your repository](#bind-your-repository) |
| `B_BINDING_MALFORMED` | Two binding lines, or a line meant as one that is not (`Astra-Binding:`, a short token) | `astra-plugin init-ci --binding <token>` rewrites the file with exactly one line; tag again. `astra-plugin check --tag` shows this before you push |
| `B_BINDING_UNUSABLE` | The token on the line binds nothing this release can use: revoked, expired, minted for another repository, or its account may not publish | Mint a new token for this repository in the panel and tag again; the panel says which of the two below applies to you |
| `B_BINDING_INVALID` | Shown only to you and to moderators: the token itself is the problem — unknown, revoked, expired, or minted for another repository | Mint a new one for this repository |
| `B_ACCOUNT_INELIGIBLE` | Shown only to you and to moderators: the account behind the token may not publish, for example because it no longer holds `astraUser` | Fix the account, then Recheck |
| `B_OWNER_CHANGED` | The repository now belongs to a different owner than the one this listing is recorded under | A transfer is an author change. It waits for a moderator; installed copies keep the old name until reinstalled |
| `B_REPOSITORY_RECYCLED` | The repository name now belongs to a different repository than the one listed | Permanent: no Recheck, tag or approval clears it. Only a moderator can reset the listing's identity |

And the release codes authors hit most:

| Code | What it means | Fix |
|---|---|---|
| `E_ATTESTATION_MISSING` | The bundle has no build attestation | You uploaded a bundle you built yourself. Let CI build it: [release with CI](release-with-ci.md) |
| `E_NO_BUNDLE_ASSETS` | The release carries no `.astraplugin` asset | The workflow did not run, or ran and failed. Check the Actions tab, attach the assets, then Recheck |
| `E_RELEASE_NOT_FOUND` | That repository has no release with that tag | A draft release is invisible to everyone but you, and a private repository looks identical to a missing one. Publish it, then Recheck |
| `E_WORKFLOW_NOT_ALLOWED` | The build ran a workflow this registry does not allow | Pin the Astra reusable workflow by commit SHA — `astra-plugin init-ci` does it — and tag again |
| `E_ASSET_URL_FOREIGN` | An asset URL is not under your repository's own releases | Every download URL must sit under `https://github.com/<owner>/<repo>/releases/download/<tag>/` |
| `E_INPUT_REPO` / `E_INPUT_TAG` | The repository or tag is not in the form expected | `you/dice-roller`, not a URL; `v0.2.0`, not a commit SHA or a branch |

The full list, with each code's title and fix, is `docs/BOT-CHECKS.md` in the
registry.

Two waits look like a stuck submission and are not:

| Code | What it means |
|---|---|
| `W_ELIGIBILITY_UNREADABLE` | The registry reads your account's eligibility from its last verified sign-in, which counts for 12 hours. Sign in to the panel and the release goes on; a `notice.sign_in` notice says the same |
| `W_REGISTRY_UNACKNOWLEDGED` | The registry's bot changed and awaits an operator's acknowledgement. Nothing is wrong with your release, and nothing is asked of you |

### What waits for a person

**Only a change of hands on a listing that already exists waits for a
moderator:**

| Event | Code |
|---|---|
| The repository or identity changed | `R_IDENTITY_CHANGED` |
| The first release of an existing listing to carry a binding line | `R_FIRST_BINDING` |
| The binding line carries a different token from the one the listing is bound with | `R_BINDING_CHANGED` |

Each of these ships another party's code, or hands the listing to another
account, as an update to people who already run it. A moderator approves it in
the panel, and it then waits the windows the registry publishes. An approved
release is still published as not reviewed, because an approval is not a
review.

A rejection carries a reason, which reaches you. You do nothing while you wait;
the panel shows the hold.

A listing that is still `grandfathered` — listed before bindings, and not bound
yet — has one more wait: from the cutover, a release of it that was held and
approved waits until the listing is bound.

### Stop, yank, appeal, report

- **Stop.** Until a release publishes, you can stop it in the panel, and it
  will not publish.
- **Yank.** After it publishes, you can yank a version in the panel. A yank is
  never undone — publish a new version instead — and it is recorded with a
  decision record, like every other decision about a listing. While your listing
  is not yet bound, ask a moderator in the panel to yank for you.
- **Appeal.** A decision about your listing that you think is wrong is appealed
  in the panel, and the answer is recorded there.
- **Ratings** are stars only: no text, no replies, no names.
- **Reports** about somebody else's plugin go through
  https://astra.minice.ai/plugins, not through GitHub. A security problem in
  Astra, the daemon, the registry or the signing chain goes to
  security@minice.ai — see [`CONTRIBUTING.md`](../../../CONTRIBUTING.md#security).

## 4 · Every release after that

Nothing. Tag, and CI does the rest: the registry detects a new tag of a listed
plugin by itself, verifies it, and the panel shows its state. There is nothing
to submit and nothing to ping. A release that has not appeared is on the
panel's page for your plugin, with its state and the reason.

**Binding is checked on every release, not only the first.** Each one is read
against the binding line at its tagged commit and the listing's identity
record, so a repository whose line changed, or that moved to another owner,
waits for a person rather than publishing — which is what makes a stolen token
or a transferred repository an event somebody sees.

## What a listing does not mean

A listing is not a safety review, and neither is a version marked reviewed:
that says a moderator read that version, and nothing more. The registry says
so in its own policy: a permission decides what the daemon will do *for* a
plugin and nothing about what the plugin's process may do to the machine. There
is no sandbox. See [the security model](../1-orientation/security.md).

## The state of this today

One thing a reader deserves to know before following this page.

**The signing chain is anchored end to end, through the catalogue and the
withdrawal list.** Precisely, and each part is checkable:

- the root keys exist on both sides — `registry/v1/root.json` carries
  `"status": "provisioned"` with two Ed25519 keys, and the daemon's
  `PRODUCTION_ROOT_KEYS` compiles in the same two;
- `registry/v1/trust.json` **is now signed** by `astra-root-2026a` and delegates
  to an index-signing key, `astra-index-2026a`. The registry's own
  `node tools/sign-trust.mjs --verify registry/v1/trust.json` confirms it and
  prints the reusable-workflow SHAs the bot will accept in an attestation — two
  of them since the tag moved on 2026-08-19: the commit `plugin-release/v1`
  points at, and the one it pointed at before. So `E_TRUST_UNPROVISIONED`, which
  used to stop every ingest, no longer fires;
- **the catalogue clients are served is signed.** Since 2026-09-20 the
  registry's signer signs `index.json` with `astra-index-2026a` and deploys it
  to Pages. The copies committed on `main`, `registry/v1/index.json` and
  `revocations.json`, carry `"signatures": []` by design, and no client reads
  them. The withdrawal list Pages serves is signed too, since astra-registry
  commit `654b942` (2026-10-05), so revocation is enforced.

See [`spec/registry-index.md` §0.1](../spec/registry-index.md) and
[the security model](../1-orientation/security.md).

What that means for you: the submission path on this page works end to end
today — your submission is read, the checks run, the panel shows the answer,
and a listing is committed, and the registry can withdraw a version from copies
already installed.

## See also

- [`spec/registry-index.md`](../spec/registry-index.md) — the index, revocations, and the verification algorithm
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — what the bot reads out of your archive
- [Versioning](../versioning.md) — what the numbers mean and how long a deprecation lasts

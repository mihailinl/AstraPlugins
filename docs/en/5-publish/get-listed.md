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
on your laptop, or an issue asking a maintainer to build it. The registry lists
release assets that CI attested, and nothing else.

Nearly every command below is `astra-plugin`; the exception is
[step 2](#2--prove-you-control-the-repository), which is one file and a `git
commit` in your own repository. If you do not have the CLI,
[install the CLI](../install-cli.md) first — there are prebuilt binaries now.

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
  · for a request through the issue form, until the registry's cutover: that `.well-known/astra-plugin-owner` on your default branch names the account opening it
  · that the id and display name do not collide with a listed plugin
  · that the licence is on the registry's SPDX allowlist
  · that the version is strictly newer than the listed one
  · the declared-vs-called host RPC scan
```

**One of those you can settle in advance, and should.** The ownership line
names the file, and committing it is [step 2](#2--prove-you-control-the-repository).
Do it before you submit and the check passes on the first run; leave it and the
first answer you get is a refusal.

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

## 2 · Prove you control the repository

**Do this before you open the issue.** It is one file and one commit, and
skipping it is the single most common way a correct, honest first submission
gets refused.

The registry has to answer one question that nothing else on this page answers:
**does the person asking for this listing control the repository being listed?**
The attestation already proves the bundle came out of that repository, and the
listing is pinned to it — but neither fact says who *you* are. Without this
step, a stranger could list somebody else's plugin and become the identity
through which its updates reach Astra users.

Commit this file to your repository's **default branch**:

<!-- doctest: illustrative reason="the path and content of a file the author writes in their own repository; there is nothing here for a runner to execute" -->
```
path      .well-known/astra-plugin-owner
content   your GitHub login, one per line
```

The one command that creates it, run at the root of your plugin's repository:

<!-- doctest: illustrative reason="git commands against the author's own repository — the runner has no such repository, and `cli` blocks must contain an astra-plugin command" -->
```bash
mkdir -p .well-known
echo 'your-github-login' > .well-known/astra-plugin-owner
git add .well-known/astra-plugin-owner
git commit -m "Declare the Astra registry owner for this repository"
git push
```

**What it proves:** somebody who can write to your default branch asserts that
this GitHub login speaks for this repository — read live at the moment the bot
checks, so removing a login stops that person opening a new listing request or
passing a `/recheck`. It does **not** reach a plugin that is already listed:
[every release after that](#5--every-release-after-that) is proved against the
account that published the release, and the listing stays pinned to this
repository either way.
**What it does not prove:** anything whatsoever about your code, which nobody
reads; it is not a signature, and it is not a safety review.

### The format, exactly

One login per line. Everything after a `#` is a comment, a leading `@` is fine,
surrounding whitespace is trimmed, and the match is case-insensitive. Only the
first 4 KB is read. So this file is valid and lists one owner:

<!-- doctest: illustrative reason="the contents of a file in the author's repository, not a command" -->
```
# owners of this repository
@Rel0d1x   # primary
```

List every person who may submit or re-submit on this repository's behalf. For
an organisation-owned repository that is usually more than one name.

### Check that the registry can read it

The bot reads the file through GitHub's contents API, unauthenticated, on the
default branch. You can make exactly the request it makes:

<!-- doctest: illustrative reason="gh against the author's own repository; `cli` blocks must contain an astra-plugin command, and this one is deliberately shell-only" -->
```bash
gh api repos/you/dice-roller/contents/.well-known/astra-plugin-owner \
  --header 'Accept: application/vnd.github.raw+json'
```

It should print your login back. If it prints `Not Found (HTTP 404)`, the file
is not where the bot looks — the usual causes are that it is on a branch other
than the default one, that it is still uncommitted or unpushed, or that the
directory is spelled `well-known` without the leading dot.

### Why this is a step and not a fallback

The registry tries three ways to establish control, and this file is the one
that works for an ordinary author. That is not a preference; it is structural,
and both of the others were watched failing on real submissions:

| Way | Why it does not answer for you |
|---|---|
| **Collaborator permission** — asking GitHub who has `admin` or `maintain` | GitHub answers that endpoint only for a caller that already has admin visibility on the repository. The registry's token belongs to the registry, so for *your* repository it gets `403` — which means "I will not tell you", not "no", and is treated as no answer at all |
| **Release author** — the account that published the release | The release workflow on [Release with CI](release-with-ci.md) creates the GitHub Release, so its author is `github-actions[bot]` rather than a person. Following the documented path is what defeats this one |
| **`.well-known/astra-plugin-owner`** | Nothing has to be visible to the registry, and nothing has to be installed. It answers |

A `403` on the first way is not held against you and never becomes a refusal on
its own. The refusal happens only when all three come back with nothing, which
is exactly what happens when this file does not exist.

## Bind your repository

**A listing is moving from a GitHub login to a Minice account.** The ownership
file above names a GitHub login, and that is how a first listing through the
registry's issue form is proved today. From the registry's cutover, every first
listing needs a **binding** instead: one more line in the same file, written by
the CLI from a token you mint in the panel, signed in to the Minice account that
will publish. Binding now costs one command and is where every listing is
going; an existing listing has until the binding deadline (below).

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
**4 · Submit in the panel.** From a bound repository, `astra-plugin publish`
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

## 3 · Submit

<!-- doctest: cli -->
```bash
astra-plugin publish
astra-plugin publish --print-url
```

It opens a prefilled issue on the registry in your browser. **It uploads
nothing and holds no credential** — there is no `astra-plugin login`, no token
in your shell history, no keyring to integrate with. `--print-url` prints the
link instead:

<!-- doctest: output from="astra-plugin publish . --print-url --repo you/dice-roller --tag v0.1.0" unrun="needs a plugin project and a real GitHub release; the flags themselves are checked by the cli block above" -->
```
dice-roller 0.1.0 — listing request for you/dice-roller@v0.1.0

  A plugin is listed once, ever. After this, releases are zero-touch: tag, let CI
  build and attest, and the registry picks it up. Everything on the store card —
  name, summary, licence, capabilities, permissions, digests — is read out of the
  attested bundle, so there is nothing else to fill in and nothing to keep in sync.

https://github.com/mihailinl/astra-registry/issues/new?template=plugin-listing.yml&title=%5Blisting%5D+you%2Fdice-roller&repository=you%2Fdice-roller&release_tag=v0.1.0
```

That capture is from a directory with no git tag of its own. Run it inside your
checkout before you have fetched the tag and one extra line appears above the
paragraph — `Note: this checkout has no tag v0.1.0.` It is a reminder, not an
error: the registry reads the release from GitHub, so what matters is that the
tag is pushed and CI has attached the assets.

> **`template=plugin-listing.yml` in that URL is load-bearing.** The template
> declares `labels: ["listing", "needs-triage"]`, and the registry's bot enters
> the submission path only for an issue carrying `listing`. Nothing else applies
> that label — not even the bot, on purpose: there it is an authority token, not
> a category, so a bot that stamped it on anything form-shaped would hand the
> exemption to anyone who can copy a form.
>
> Two real listing requests were lost exactly this way: they arrived unlabelled,
> triage returned `mode: "none"`, the check, publish and comment steps were all
> skipped, and the authors got **no answer at all, not even a refusal**. That is
> fixed on both sides now. Blank issues are disabled on the registry, so the
> *New issue* page offers only forms; and an unlabelled request that does arrive
> gets a comment saying exactly what is missing, plus the one click — a
> maintainer adding `listing` — that starts verification on that same issue with
> nothing retyped. Opening it from this link still skips all of that.

The submission carries **two facts**:

| Field | Why it is typed rather than read |
|---|---|
| Source repository (`you/dice-roller`) | The bundle cannot vouch for where it is served from |
| Release tag (`v0.1.0`) | Same |

Plus three confirmations, all required: that you have committed
`.well-known/astra-plugin-owner` to the default branch with your login in it,
that you own or maintain the repository, and that you have read the policy.

**Everything else is read out of the attested bundle** — the id, the version,
the display name, the summary, the licence, the capabilities, the permissions,
the platforms, the digests, the sizes. That is not a convenience: everything in
the bundle is covered by the attestation, which makes it strictly more
trustworthy than anything typed into a form. It also deletes a whole class of
rejection, because there is no form for `plugin.toml` to disagree with.

## 4 · What happens after you submit

This section is the one two real authors needed and did not have. It describes
the registry's flow as `astra-registry/docs/POLICY.md` and `docs/BOT-CHECKS.md`
define it; both are generated from or asserted against the bot's own code
(`bot/lib/policy.mjs`, `bot/lib/codes.mjs`), so the numbers here cannot quietly
drift from the code that keeps them.

**Two paths, and they wait for different things.** Everything below, up to
[On the panel path, from the cutover](#on-the-panel-path-from-the-cutover),
describes a request through the registry's issue form, which is how a first
listing is made today. From the registry's cutover, a release reaches the
registry through the Astra plugins panel instead, and **a release that passes
every automatic check is published at once**, marked as not reviewed by Astra
moderators. There, only a change of hands on a listing that already exists
waits for a moderator.

### The sequence

1. **Your issue gets the `listing` and `needs-triage` labels** — from the issue
   template, automatically. This is the step that decides whether anything
   happens at all; see the warning in §3.
2. **The bot triages it**, reads your two facts, fetches the release from GitHub
   unauthenticated, and runs every check in `docs/BOT-CHECKS.md` against the
   bytes: the attestation and which workflow produced it, that the asset URLs sit
   under your own repository's release namespace, that you control the
   repository ([step 2](#2--prove-you-control-the-repository)), the archive's
   structure, the manifest, the licence, the version ordering, and the
   declared-versus-called host RPC scan.
3. **The bot comments on your issue** with the outcome, the reason, and — when
   there is one — the exact time it will publish. You are told either way.

If nothing has commented within an hour, check the issue's labels. No `listing`
label means step 1 did not happen and nothing downstream ran.

### The four outcomes

On the issue form:

| Outcome | Means | Who is involved |
|---|---|---|
| **Published** | Committed, and in the catalogue on the next index build | nobody |
| **Delayed** | Everything passed; it publishes itself at a stated time | nobody |
| **Held** | A decision the registry is not entitled to make automatically | a maintainer, within 48 h |
| **Refused** | A check failed. The policy never got a say | you: fix it and comment `/recheck` |

A release publishes itself with no human when all of these hold: it comes from
the repository already listed for that plugin, every bot check is green, the
version is strictly newer, it asks for no high-risk permission it did not
already have, and it asks for no new permission or capability at all. Drop only
the last and it still self-publishes, after a delay.

**On the issue form, a first listing is never one of those.** It is held for a
person by definition — see below — so there the answer to "how long until my
first plugin is listed" is *up to 48 hours after the bot comments*, not
*minutes*. On the panel path, from the cutover, it is minutes: see
[below](#on-the-panel-path-from-the-cutover).

### How a hold is cleared

Nothing is required of you. On the issue form, a maintainer comments
**`/approve`** on your issue, and the entire ingest then runs again from scratch
against the bytes as they are at that moment — an approval is a "a person said
yes, at this time" marker and carries no cached verdict, so approving something
does not skip a single check.
**`/reject <reason>`** is the other half, and it must carry a reason, which is
posted to you. Both commands are permission-checked against the registry
repository: the commenter needs `admin` or `maintain` there, re-proved through
GitHub's API at the moment the command is read rather than trusted from the
event payload, and a command from anyone else is answered rather than ignored.

You do not type either command, and you do not need to do anything while you
wait. They are documented here only so that "held for a maintainer" names a
mechanism rather than a silence.

*One caveat, stated because this page's rule is to state them:* this
maintainer-command path is landing in the registry at the same time as this
page. If your hold predates it, the outcome is the same and the SLA is the same
— a maintainer still decides — but the decision may be recorded by hand rather
than by the command.

### What a refusal looks like

The bot comments with a fixed code and what to do about it. A refusal is not a
verdict on your plugin; it is a named, fixable condition. The ones authors hit
most:

| Code | What it means | Fix |
|---|---|---|
| `E_ATTESTATION_MISSING` | The bundle has no build attestation | You uploaded a bundle you built yourself. Let CI build it: [release with CI](release-with-ci.md) |
| `E_NO_BUNDLE_ASSETS` | The release carries no `.astraplugin` asset | The workflow did not run, or ran and failed. Check the Actions tab on your repository |
| `E_RELEASE_NOT_FOUND` | That repository has no release with that tag | A draft release is invisible to everyone but you, and a private repository looks identical to a missing one |
| `E_WORKFLOW_NOT_ALLOWED` | The build ran a workflow this registry does not allow | Pin the Astra reusable workflow by commit SHA. `astra-plugin init-ci` does it for you |
| `E_ASSET_URL_FOREIGN` | An asset URL is not under your repository's own releases | Every download URL must sit under `https://github.com/<owner>/<repo>/releases/download/<tag>/` |
| `E_OWNERSHIP_UNPROVEN` | Nothing proved that you control that repository | You almost certainly skipped [step 2](#2--prove-you-control-the-repository). Commit `.well-known/astra-plugin-owner` on the default branch with your GitHub login in it, then comment `/recheck` — no new release and no new tag is needed |
| `E_INPUT_REPO` / `E_INPUT_TAG` | The repository or tag is not in the form expected | `you/dice-roller`, not a URL; `v0.2.0`, not a commit SHA or a branch |

After you fix it, comment **`/recheck`** on the same issue. Every check runs
again from scratch against the bytes as they are at that moment; nothing is
resumed and nothing queued is trusted. The full list, with the exact wording of
each failure, is `docs/BOT-CHECKS.md` in the registry.

The bot's own exit codes are `0` listed · `1` refused · `3` held for a
maintainer · `2` the bot itself failed. The last is deliberately distinct: "your
plugin is bad" and "our tooling is bad" must never render as the same comment to
a stranger.

### What needs a person on the issue form

Three events, and the list does not grow without a change to the registry's
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

A check may separately hand a decision to a person — a name one edit away from a
listed plugin, a display name that collides with one. That arrives as
`R_CHECK_HELD`, is not one of the three, and carries the same SLA.

**The SLA is 48 hours** for those, from the moment the bot comments. There is
one maintainer, which is precisely why the list is three items long. The
registry publishes what happens when that slips, rather than only the promise:
past 96 hours the maintainer must either publish the queue or move the
triggering event out of the blocking set, in a reviewed commit that also edits
the paragraph making the promise.

### When a release waits instead

On the issue form, some releases pass everything and still do not publish
immediately:

| Situation | Code | Delay |
|---|---|---|
| The plugin holds **any** high-risk permission, whether or not this release changed it | `P_DELAY_HIGH_RISK` | 24 h |
| The release asks for a permission or capability the previous one did not, inside the non-high-risk set | `P_DELAY_WIDENED` | 24 h |
| Either of the above, from an author with **5 clean** releases in this registry | `P_TRUSTED_AUTHOR` | 6 h |

The bot states the exact publication time, and when the clock runs out the
entire ingest runs again from scratch against the bytes as they are then. The
delay buys one thing and the registry does not claim more: a window in which an
author whose GitHub account was taken over can see a release they did not make
and say so.

### On the panel path, from the cutover

*Amended 2026-09-26 (registry contract 3.0.0).* Before this date, this page
said that a first listing is always held for a person. On the issue form it
still is, until the cutover removes the form. The registry's own rule is
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

## 5 · Every release after that

Nothing. Tag, and CI does the rest; the registry notices the release and
regenerates the index.

If it has not noticed:

<!-- doctest: cli -->
```bash
astra-plugin publish --notify
```

That is the manual ping for a plugin that is **already listed**. Without it,
`publish` opens a first-listing request.

**Ownership is a different question on this path.** A ping, and the cron
backstop behind it, proves the release against the account that *published*
it — not against whoever typed the ping, and not against
`.well-known/astra-plugin-owner`. Editing that file therefore does not change
who can ship a release of a plugin that is already listed. What bounds this is
that a ping may only name a repository the registry has **already pinned**: a
change of repository stops being routine and goes back to a person.

## What a listing does not mean

A listing is not a safety review, and neither is a version marked reviewed:
that says a moderator read that version, and nothing more. The registry says
so in its own policy: a permission decides what the daemon will do *for* a
plugin and nothing about what the plugin's process may do to the machine. There
is no sandbox. See [the security model](../1-orientation/security.md).

## The state of this today

One thing a reader deserves to know before following this page.

**The signing chain is anchored through the catalogue, and not yet through the
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
  them. The withdrawal list Pages serves is still the unsigned committed one,
  so revocation enforcement is not live yet.

See [`spec/registry-index.md` §0.1](../spec/registry-index.md) and
[the security model](../1-orientation/security.md).

What that means for you: the submission path on this page works end to end
today — your issue is read, the checks run, the bot answers, and a listing is
committed. What is still pending is the signed withdrawal list on Pages, which
lets the registry withdraw a version from copies already installed. Nothing on
this page changes when it lands.

## See also

- [`spec/registry-index.md`](../spec/registry-index.md) — the index, revocations, and the verification algorithm
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — what the bot reads out of your archive
- [Versioning](../versioning.md) — what the numbers mean and how long a deprecation lasts

# The security model

Read this before you publish anything, and before you install anything.

## The one sentence

**A plugin is a native process running with your full user account's
privileges.** It can read your files, open sockets, and spawn programs. Nothing
in Astra sandboxes it, isolates it, or restricts it at the operating-system
level.

That is not a gap this page is glossing over — it is the design as it stands.
Isolation is **Phase 7** of the production plan, it is named there so that it is
a decision rather than an omission, and it is **not implemented**. Candidate
work, when it happens: Landlock + seccomp on Linux, a low-integrity token or
AppContainer on Windows, rlimits. Until then, "signed" and "listed" say nothing
about what the process can do to your machine.

Anywhere Astra could imply otherwise it is *required* to say this out loud — the
install consent sheet and the provenance panel both carry a permanent block
stating that an attestation does not prove the code is safe. The daemon already
says it in the message it refuses an unverified install with: *"a plugin runs as
a native process with your full privileges, so an unverified one can take over
your machine"* (`astra-daemon/src/plugins/manager.rs`). What the app's own
screens look like is Astra's to document, not this repository's; this page
describes the daemon, the CLI and the formats.

## What each mechanism actually answers

Four layers, four different questions. Confusing them is how "it's signed"
becomes "it's safe".

| Layer | Mechanism | Verified by | Answers |
|---|---|---|---|
| 1. Build provenance | GitHub artifact attestation (Sigstore keyless, OIDC) | the registry bot, in CI | "these bytes came from workflow W at commit C in repo R" |
| 2. Distribution trust | Ed25519 countersignature over the artifact digest, in a signed index | the daemon, offline | "Astra listed exactly these bytes, and they have not been withdrawn" |
| 3. Identity continuity | a TOFU pin of `github:owner/repo` | the daemon, offline | "this update is from the same author as the install" |
| 4. Runtime authority | `[permissions]` + `require_permission` at every host RPC | the daemon, on every call | "what may this plugin ask Astra to do" |

None of them answers "is this code safe". That question has no mechanical
answer, and a system that implies it does is worse than one that admits it does
not.

## Two things that are true today and will not be softened

### The trust chain is specified, implemented, and not anchored

The root keys that would make a signed catalogue verifiable **have not been
generated**. Concretely
([`spec/registry-index.md` §0.1](../spec/registry-index.md)):

- the registry's `root.json` carries `"status": "unprovisioned"` and an empty
  `roots` array;
- the daemon's `PRODUCTION_ROOT_KEYS` is an empty table, deliberately — *a
  shipped Astra must never trust a key that is published in a repository*;
- therefore every catalogue today classifies as `UNSIGNED` with reason
  `NoTrustAnchor`, and the registry bot stops every ingest at
  `E_TRUST_UNPROVISIONED`;
- and because withdrawal lists are verified strictly, an unsigned one is
  refused, so **revocation enforcement is not live either**.

A default build therefore fails closed. Nothing here is a promise about a
guarantee you have today; it is a description of a mechanism that starts
carrying weight the day two public keys appear in two places.

### A local signing key confers no trust at all

`astra-plugin keygen` and `astra-plugin sign` exist. They are an optional
second factor — defence in depth against a GitHub account takeover, where the
value is that the key lives somewhere a stolen GitHub session is not.

They are **not** what makes Astra install a plugin, and a bundle signed with
your own key is untrusted in exactly the way an unsigned one is. The daemon
checks the in-ZIP `SIGNATURE`/`PUBKEY` pair against a *pinned Astra publisher
key*, never against the key inside the archive. `astra-plugin build` says so
every time it runs:

<!-- doctest: output from="astra-plugin build ." -->
```
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
```

and `astra-plugin sign` says so on success, deliberately not buried in `--help`:

<!-- doctest: output from="astra-plugin sign <bundle>" -->
```
This signature is an optional second factor, not a trust signal.

Astra does not verify it against your key — the daemon checks the in-ZIP pair against a
pinned Astra publisher key, so a bundle signed with your own key is untrusted by
construction, exactly as an unsigned one is.
```

The in-ZIP pair is a retiring format feature; both the command and the entries
it writes are scheduled for removal.

There is no `astra-plugin login`, and there will not be one: publishing carries
a repository and a tag, so there is no credential to store and none to leak.

## What the permission gate does

The daemon enforces `[permissions]` at one place: `require_permission`, on six
of the ten `PluginHostService` RPCs. The other four — `Register`,
`GetPluginSelfConfig`, `PluginLog` and `GetDaemonInfo` — are **always allowed**
and run no permission check at all; they are `(…, None)` in the daemon's
`HOST_RPC_PERMISSIONS` table and there is no `require_permission` call in their
bodies. A registered plugin with an empty `[permissions]` block can reach those
four and nothing else. Why they are free is
[in the permissions reference](../3-reference/permissions.md#the-four-calls-that-need-nothing).
The table `require_permission` reads —
`HOST_RPC_PERMISSIONS` in the daemon — is pinned to
[`spec/hooks.yaml`](../../../spec/hooks.yaml) by parity rule R6, so the
generated [permission column](../reference/parity.md) cannot drift from the code
that enforces it.

Two independent gates, and both must pass
([`spec/permissions.md` §4.2](../spec/permissions.md)):

1. **the grant** — a per-install answer that a consent sheet produced and a
   trust record holds;
2. **the ceiling** — a per-provenance rule that no record can buy past.

The manifest is a *request*. For tiers 1 and 2 the granted set lives where the
plugin cannot write it, because a plugin that could widen its own grants by
editing its own manifest would have a permission system that is a comment.

**Tier 3 is the exception, and it is deliberate.** For a sideloaded source
directory the daemon's `decide_grants` returns `declared.capped(|_| true)` —
the manifest *is* the consent record, read from the plugin's own directory on
every load, with no ceiling above it. A sideloaded plugin can therefore widen
its own permissions by editing its own `plugin.toml` between restarts, up to the
whole vocabulary. That is one more reason Developer Mode is a developer tool and
not an install path.

Five permissions are high-risk and each gets its own consent checkbox:
`send_chat_message`, `push_to_ui`, `set_theme_contribution`, `dom_access`,
`client`. `dom_access` gets a second screen. Details, including how to write a
`reason` that is worth reading: [permissions](../3-reference/permissions.md).

## Where a plugin came from decides its ceiling

| Tier | Source | Ceiling |
|---|---|---|
| **1 · Registry** | installed from the store, verified | everything it asked for, subject to consent. No override on a verification failure |
| **2 · Local file** | a `.astraplugin` imported by hand | `send_chat_message`, `set_theme_contribution`, `dom_access` and `client` are **refused outright, not warned about** |
| **3 · Sideload** | a source directory, Developer Mode on | **no ceiling** — and it never auto-starts |

Tier 3 is uncapped on purpose: it is the authoring loop for UI plugins, and
capping it would make `dom_access` undevelopable. It is also gated behind an
explicit setting, never starts by itself after a restart, and is
[documented as a developer tool](../5-publish/sideload.md) rather than as a way
to install things.

Four states get **nothing**, whatever the manifest says: `Untrusted`,
`TamperDetected`, `Revoked`, and a `Verified` plugin whose record cannot be
believed. A plugin installed before trust records existed (`Unrecorded`) gets
its manifest capped at the Tier-2 ceiling — "arrived from somewhere, proved
nothing" is exactly that shape.

## What is not defended against

Named, rather than left for a reader to discover:

| Threat | Status |
|---|---|
| A plugin reading your files, your keys, your network | **Not defended.** No isolation exists — Phase 7 |
| A plugin reading `daemon.token` and registering as a client | **Not defended.** Same reason |
| A malicious or compromised registry serving different bytes | Defended *by design* — the index countersigns a digest and the daemon re-hashes — **but not in force**: the roots are provisioned (`registry/v1/root.json`, the same two keys compiled into the daemon), and the catalogue index they sign is still unsigned |
| A withdrawn version already installed | Specified; not enforced today, because an unsigned withdrawal list is refused |
| Another local process calling into your plugin's capability server | **Defended.** The daemon presents the spawn token on every call and sets `ASTRA_PLUGIN_CAPABILITY_AUTH=require`, so the SDK refuses a call without it. Under a daemon too old to send the header the SDK stays at `warn` — a wrong token refused, a missing one accepted — because there is nothing else it could do |
| A plugin editing its own manifest to widen its permissions | **Defended at tiers 1 and 2** — grants come from a daemon-owned trust record, not from the manifest. **Not defended at tier 3**: for a sideloaded directory the manifest *is* the grant and has no ceiling, so it can take every permission in the vocabulary by editing its own file |
| A hand-planted sideload marker | Defended. The daemon refuses a marker it did not write |

## For users, in one paragraph

Install from inside Astra. The store path pins the artifact by digest and
verification failures are hard blocks with no override. If someone sends you a
`.astraplugin` file, importing it is a decision you are making about that
person, and four permissions will be refused whatever the file asks for. If
someone tells you to turn on Developer Mode and point Astra at a folder, they
are asking you to run unsigned code as yourself.

## See also

- [`spec/registry-index.md`](../spec/registry-index.md) — the document formats and the verification algorithm, normatively
- [`spec/permissions.md`](../spec/permissions.md) — grants, ceilings, consent, `permissions_hash`
- [`spec/bundle-v2.md`](../spec/bundle-v2.md) — what is inside a `.astraplugin` and what a verifier must reject
- [Troubleshooting](../6-operate/troubleshooting.md) — what each verification failure means when you hit one

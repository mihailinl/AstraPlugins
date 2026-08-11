# Permissions — normative specification

**Status:** normative. The vocabulary, the gate, the ceilings, the four
provenance paths and the hash are all implemented and enforced; where something
is specified but not yet enforced this document says so in the row.

Requirement words are RFC 2119.

Two orthogonal sections exist in `plugin.toml`, and confusing them is the bug
this vocabulary was created to fix:

| section | direction | question |
|---|---|---|
| `[capabilities]` | daemon → plugin | *what do I implement, that Astra may call into?* |
| `[permissions]` | plugin → daemon | *what may I call out to, and what surfaces may I be handed?* |

They were one word for two things, and the word meant the first one — which is
how `dom_access` came to be a capability a plugin granted itself by declaring it.

---

## 1. The vocabulary

Eight ids, a closed set (`astra-plugin-manifest/src/permissions.rs`,
`PERMISSION_NAMES`, pinned to the enum by test). The registry validates a
listing's ids against this list and Astra's localised label table is keyed by it,
so an id added in one place and not the others renders as a blank row.

| id | gates | what it grants | high risk |
|---|---|---|---|
| `fire_trigger` | `PluginHostService.FireTrigger` | run the user's saved automations | |
| `subscribe_events` | `SubscribeEvents` | receive daemon events, **restricted to the declared types** (§1.1) | |
| `set_variable` | `SetVariable` | write into the daemon's variable context, namespaced to the calling plugin | |
| `send_chat_message` | `SendChatMessage` | drive an AI turn — spend the user's tokens, speak in their assistant's voice | ● |
| `push_to_ui` | `PushToUi` | push an event at the Astra window | ● |
| `set_theme_contribution` | `SetThemeContribution` | restyle the whole app | ● |
| `dom_access` | *no RPC* — a **surface** | run the plugin's own script inside the Astra window, with access to the user's conversations and to every other plugin's interface | ● |
| `client` | *no RPC* — a **surface** | act as a client front-end: its own chat surface, its own session | ● |

**The five marked ● are high risk** (`HIGH_RISK_PERMISSIONS`) and each gets its
own consent checkbox. The plan's §4.3 spells four checkboxes and omits
`push_to_ui`; §5.6 lists five. The implementation takes the **union**, because
the disagreement is between a UI paragraph and the security section, and a
checkbox too many costs a click while one too few costs the property.

**`dom_access` and `client` gate no RPC**, which is exactly why they need a
second enforcement point: they are enforced where the *surface* is handed out
(§4.2), not where a call is answered.

### 1.1 Permission arguments

A `[permissions]` entry is an object, not a bool:

```toml
[permissions]
fire_trigger     = { reason = "Fires the on_dice_roll trigger you configure" }
subscribe_events = { types = ["command_completed"], reason = "Reacts when a command finishes" }
set_variable     = { scopes = ["plugin"] }
```

| member | type | meaning |
|---|---|---|
| `reason` | string, ≤ 140 chars | the author's own words (§6) |
| `types` | array of string | **`subscribe_events` only.** The event-type allowlist |
| `scopes` | array of string | **`set_variable` only.** `plugin` / `session` / `persistent`. **Reserved** — the daemon namespaces every plugin write by plugin id today, so this narrows nothing yet. It is parsed so that a manifest declaring it is publishable and hashes identically everywhere |

**`subscribe_events.types` is an allowlist the daemon enforces per event, and an
empty one allows nothing.** Three states, and the middle one is the whole point:

* permission absent → no stream at all;
* permission held, `types` empty → **allows nothing**; the daemon refuses the
  subscription with a message naming the fix, rather than handing back a stream
  that is silent forever;
* `types` listed → exactly those `AstraEvent::event_type_str()` values.

The intuitive reading — "no filter means everything" — is the hole this
permission exists to close: an unfiltered subscriber receives
`speech_recognized`, which is every word the user says.

### 1.2 Unknown ids are kept, not refused

A manifest naming an id this build has never heard of is **accepted**. Two
reasons, and both point the same way:

1. **Forward compatibility.** New ids ship with new Astras. A daemon that refused
   an unknown id would make every addition a flag day for every older daemon.
2. **The hash.** `permissions_hash` (§5) is computed over these bytes by three
   implementations. Dropping a key the reader did not recognise would make two
   of them disagree about what was signed.

An unknown id is **inert** — default-deny means it grants nothing, ever — and it
is not silent. The consent sheet renders it through its
`permission.unrecognised` label rather than dropping it, so a user is told the
plugin asks for something this version of Astra does not know about.
`Permissions::unknown()` exists so tooling can itemise them; **`astra-plugin
check` does not do so today** — it reports that a `[permissions]` section is
present and stops there.

(`[capabilities]`, by contrast, is `deny_unknown_fields`: it is a closed set of
bools where a typo reads exactly like `false`.)

## 2. Default-deny, and the four RPCs that need nothing

**An absent `[permissions]` section grants no host RPCs beyond the always-allowed
set.** A missing section is not "unspecified"; it is a complete answer, and the
answer is no.

The always-allowed set is four, and it is written down as a table
(`HOST_RPC_PERMISSIONS` in `host_service.rs`) that two canaries check every RPC
against, so an ungated new RPC is a test failure rather than a silent omission:

| RPC | permission |
|---|---|
| `Register` | — |
| `PluginLog` | — |
| `GetPluginSelfConfig` | — |
| `GetDaemonInfo` | — |
| `SubscribeEvents` | `subscribe_events` |
| `SendChatMessage` | `send_chat_message` |
| `FireTrigger` | `fire_trigger` |
| `SetVariable` | `set_variable` |
| `SetThemeContribution` | `set_theme_contribution` |
| `PushToUi` | `push_to_ui` |

`GetDaemonInfo` is the one addition to the plan's list of three, and it is a
decision rather than an omission: it returns `version`, `state`, `grpc_port` and
`language`, all of which `PluginRegisterResponse` already handed the caller, so
it discloses nothing new. Inventing a permission id for it would put a checkbox
in front of the user that protects nothing, and boxes that protect nothing are
how users learn to tick boxes.

**`client_session_token` is issued to every plugin.** The token is
*authentication* (who is calling), not *authorization* (what they may do).
Withholding it from non-`client` plugins would deny `PluginLog`,
`GetPluginSelfConfig`, `SubscribeEvents` and `FireTrigger` — the always-allowed
set — and break every plugin and both in-tree sidecars. The `client` gate belongs
in the ceiling and on the specific surfaces, not in the token.

## 3. Declaring is asking; granting is a different object

**Nothing in a `plugin.toml` is a grant.** A `[permissions]` block is the
author's *request*. The **granted set** is a separate object the daemon resolves
per provenance path and stores where the plugin cannot reach it —
`<base_dir>/registry/records/<id>.json`, a sibling of the plugins tree and never
a child of it, MAC'd with a daemon-held key.

Enforcement reads the granted set and never the manifest — the shape of the call
at the top of each gated RPC (illustrative excerpt from `host_service.rs`, not a
runnable sample):

```rust
let (plugin_id, grants) =
    self.require_permission(&request, Permission::FireTrigger, "FireTrigger").await?;
```

A plugin that could widen its own grants by editing its own manifest would have a
permission system that is a comment. That was literally true before Phase 4:
`[capabilities] dom_access = true` — one line in a file inside the plugin's own
directory — was copied straight onto the UI contribution the renderer honours by
loading the plugin's script into the Astra window itself.

**Why the record is not in the plugin's directory.** The plugin runs as the user,
with `current_dir` set to its install directory. Mode 0600 protects against other
users, not against the subject. A record the subject can write lets a malicious
plugin grant itself `dom_access`, overwrite the TOFU pin, rewrite
`artifact_sha256` to evade digest-keyed revocation, and rewrite the per-file
hashes so the start-time re-check passes.

### 3.1 The capability bridge

`dom_access` and `client` are `[capabilities]` bools **and** permission ids.
Every plugin written before the split says what it wants in the old place —
including `companion`, `doom` and `bad-apple`, none of which declares a
`[permissions]` section at all.

So a `[capabilities] dom_access = true` bit is read as **a request**, exactly like
a `[permissions]` entry, and gets exactly the same answer from the same table
(`declared_permissions()`). The bridge is deliberately *not* "the capability bit
grants the permission": it puts the bit where a request lives, so there is one
answer to "may it?" and not two.

Consequence for authors: **a plugin published through the registry must declare
`[permissions] dom_access`**, because a registry install grants from its trust
record, which is written from the bundle's `MANIFEST.json` `[permissions]` block
— and that entry is what the consent sheet renders and the user ticks.

## 4. Where the granted set comes from

### 4.1 The four provenance paths

`decide_grants()` is this table as one pure function.

| path | granted set |
|---|---|
| **Built-in sidecar** (`builtin_stt`, `builtin_vox`) | a **code-declared** set next to that sidecar's `build_manifest()`. No trust record, no disk read — a sidecar has no record *by design*, so a code path that looked for one would be a code path that can fail for it |
| **Registry install** | the trust record written at install: the bundle's `MANIFEST.permissions`, after the consent check, capped by the tier's ceiling |
| **`ImportPluginFile`** (a `.astraplugin` from out of band) | a trust record at `tier: "local-unverified"` — the manifest's declared set **capped by the Tier-2 ceiling** |
| **Sideload** (a source directory, Developer Mode) | a trust record at `tier: "sideloaded"` — the manifest's declared set, **uncapped** |

Four branches are *not* in that table and are equally normative:

| state | granted |
|---|---|
| `Untrusted` — a record was expected and cannot be believed | **nothing** |
| `TamperDetected` — a file no longer matches the digest recorded for it | **nothing** |
| `Revoked` — a signed withdrawal list covers it | **nothing** |
| `Unrecorded` — installed before trust records existed, no record at all | the manifest's declared set, **capped by the Tier-2 ceiling** |

`Untrusted` can still be started by hand, and when it is, it runs with no grants:
"the user asked" is not evidence about bytes. `Unrecorded` is capped rather than
refused because granting those plugins nothing would break working installs on
upgrade with no way for the user to fix it, and granting them their manifest
uncapped would let any of them self-grant `dom_access` by editing a file in their
own directory. The Tier-2 ceiling is exactly the shape of "arrived from
somewhere, proved nothing".

A `Verified` plugin with no believable record gets **nothing**: `Verified` *means*
a believable record, and the answer to the impossible combination is not to fall
back to the manifest.

Every denial names its source (`GrantSource::describe`) — "denied" without "and
here is the source that had nothing to say about it" is the failure mode that
gets a permission system reverted.

### 4.2 Two gates, not one

A permission is honoured only when **both** hold:

1. the **grant** — a per-install answer a consent sheet produced and a trust
   record holds;
2. the **ceiling** — a per-provenance rule no record can buy past.

`require_permission` asks the first for the six host RPCs that gate a
permission — `SubscribeEvents`, `SendChatMessage`, `FireTrigger`, `SetVariable`,
`SetThemeContribution`, `PushToUi`. The remaining four (`Register`,
`GetPluginSelfConfig`, `PluginLog`, `GetDaemonInfo`) carry `None` in
`HOST_RPC_PERMISSIONS` and are always allowed; §2 has the table and the
reasoning.
`ceiling_admits`
asks the second wherever a *surface* is handed out — `PluginStatusMsg`, the
UI-contributions response, the active-themes response — so the renderer never
receives a value it could honour. A plugin missing from the grants map is
refused: "resolved nothing about it" is not a reason to serve it the
highest-risk surface in the system.

## 5. Tier ceilings

| tier | source | ceiling |
|---|---|---|
| **1 · Registry** | verified per the install algorithm | **everything**, subject to consent. No override on failure |
| **2 · Local file** (`ImportPluginFile`) | a `.astraplugin` received out of band | `send_chat_message`, `set_theme_contribution`, `dom_access` and `client` are **refused outright, not warned about** |
| **3 · Sideload** | a source directory the user pointed a file dialog at, Developer Mode on | **none** — and it **never auto-starts**: Developer Mode is required at load time and a restart leaves it stopped until the user starts it again |

Sideload's tier is surfaced to the user as `provenance.tier.sideloaded`
("loaded from a folder") in the provenance panel. The plan also asks for a
permanent non-dismissible "DEVELOPER — unverified code from a local directory"
badge on the card and on the window chrome for `dom_access`; **that badge is not
in the UI today** and this document does not claim it.

**Tier-2 promotion is not implemented.** The plan describes promoting an
imported file to Tier 1 when its digest appears in a fresh index and the version
floors hold; today `import_plugin_file` passes no verified release into the
install path, so an imported bundle is **always** `local-unverified`, whatever
the index says about its digest. Do not tell an author that publishing will
retroactively lift the ceiling on a file they mailed someone.

The Tier-2 refusal list is `TIER2_REFUSED_PERMISSIONS` — deliberately **not** the
same list as `HIGH_RISK_PERMISSIONS`: `push_to_ui` is worth a checkbox and is not
worth refusing a file the user chose to import. The four are quoted from §5.5,
not inferred.

**Tier 3 is not Tier 2 with a nicer badge.** The split is by *intent*, not by
verification status. A user who pointed a file dialog at a directory on their own
disk has given a stronger signal than an unverified file that arrived from
elsewhere — and `companion`, `doom` and `bad-apple`, this project's own flagship
examples, all need the DOM path that Tier 2 refuses. Capping Tier 3 would make
`astra-plugin dev` impossible.

Unknown ids are dropped by every ceiling (`capped()` filters on
`Permission::from_id(id).is_some_and(keep)`): a ceiling that let through the ids
it could not classify would be a ceiling with a hole shaped like the next
release.

**The design rule, held to everywhere:** *the only thing a user override can buy
is the right to run code from a source Astra has not vetted. It can never buy a
permission that a verified plugin would have had to ask for.*

## 6. Consent

The consent sheet is rendered **before any download**, from the catalogue
record's `permissions` — which the registry copied from the bundle's
`MANIFEST.json` at ingest.

* Each id is rendered through **Astra's own localised label table**. The author's
  `reason` is subordinate: quoted, plain text, ≤ 140 characters, always prefixed
  *"The author says:"*. It is never the label itself — wording fixes ship with
  Astra and must not be craftable by a listing.
* Each high-risk permission gets its **own checkbox**; `dom_access` gets a
  second screen.
* The answer travels into the install as a **ceiling, not a request**
  (`InstallOptions::consent`): the install is refused with
  `PERMISSIONS_NOT_CONSENTED` if the *bundle* asks for anything the sheet did not
  show. The two lists come from different places — the sheet renders the
  catalogue record, the trust record grants the bundle's own manifest — and
  nothing else makes them agree. A listing that declares nothing while shipping a
  bundle that asks for `dom_access` is the "malicious registry" case aimed
  straight at the consent screen.
* `consent: None` — the unary install, an import, a test, an adoption — keeps the
  pre-consent behaviour: grant the bundle's declared set, capped by tier.

**Updates.** A version asking for a permission the installed version was not
granted is refused with `PERMISSIONS_WIDENED` and becomes a review prompt; the
user's explicit approval is what turns it into an install. Comparison is **by
permission name, never by the whole request object**: an author who improves the
wording of a `reason` has not widened anything, and an update gate that treated
that as a widening would train users to click through the one dialog that
matters.

**Withdrawal takes effect immediately.** On any change to `granted_permissions`,
on consent decline, and on revocation, the daemon drops the server-side
subscription and invalidates the session token, so a live event stream cannot
survive a narrowing. The plugin is told which of them happened through the
`x-astra-teardown-reason` trailer (`grants_changed`, `consent_declined`,
`revoked`, `trust_lost`, `disabled`, `uninstalled`, `re_registered`) — a stable
token, so an SDK never has to parse English to know whether retrying is
pointless.

### 6.1 Writing a good `reason`

It is shown to a user who is deciding. It **MUST** be ≤ 140 characters and
**SHOULD**:

* name the **feature the user recognises**, not the API — *"Fires the
  on_dice_roll trigger you configure"*, not *"calls FireTrigger"*;
* say **when**, if it is not always — *"only while a recording is in progress"*;
* avoid restating the permission's own label; Astra already renders that;
* avoid urgency, threats or instructions to the user. The generator refuses text
  containing bidi overrides or zero-width joiners anywhere it is displayed
  verbatim, and a consent sheet is the last place to make an exception.

A permission with no plausible reason is a permission to remove from the
manifest — nothing checks that automatically, and a reviewer reading the listing
is the only backstop.

## 7. `permissions_hash`

```
permissions_hash = "sha256:" ‖ lowercase_hex( SHA256( JCS(permissions) ) )
```

* `JCS` is RFC 8785 canonical JSON — keys sorted by UTF-16 code unit, compact.
  See [`registry-index.md` §3](registry-index.md#3-canonicalisation-jcs-profile)
  for the profile both repositories implement.
* **`null` and `{}` are the same value** and hash the same, so a producer that
  omits the member and one that writes an empty object agree:
  `sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`.
* **Empty members are omitted, not emitted empty.** `set_variable = {}` is `{}`,
  never `{"reason":""}`. Two canonical spellings of one declaration are exactly
  the drift this hash exists to prevent.
* The `sha256:` prefix is part of the value, because it crosses a repository
  boundary.

Three implementations compute it and all three are compared:
`astra-plugin`'s packer writes it into `MANIFEST.json`; the registry bot
re-derives it at ingest and refuses to list a mismatch
(`E_PERMISSIONS_HASH_MISMATCH`); the daemon re-derives it before it believes the
manifest and blocks the install (`PERMISSIONS_HASH_MISMATCH`). Golden vectors:
`ok-permissions` (a correct non-empty map) and `permissions-hash-mismatch` — see
[`bundle-v2.md` §10](bundle-v2.md#10-permissions-and-permissions_hash) and the
F5 divergence, which is the CLI's reader alone.

The hash is also recorded in the trust record and re-checked at discovery, so a
`plugin.toml` edited in place after install is detected rather than obeyed.

## 8. What permissions are not

`[permissions]` answers *what the daemon will do for a plugin*. It does not
answer *what the process can do to the machine*.

A plugin is a native process, started by the daemon, running as the user with
their full privileges. It can read the user's files, open sockets, and — today —
read the daemon's own token from disk. **There is no sandbox.** Isolation
(Landlock/seccomp, an AppContainer or low-integrity token on Windows, rlimits) is
scoped as future work and is explicitly not in this release.

Two consequences this document holds every consumer to:

* **Astra's UI must never imply a sandbox.** The provenance panel's "does not
  prove" block and the consent sheet's one-liner exist for exactly this reason.
* **A permission denial is a real boundary only for the daemon's own
  authority** — the automations, the chat turn, the theme, the window. It is a
  tripwire, not a jail, for everything else.

Being honest here is not a caveat bolted on the end. A permission model that is
described as a sandbox is a permission model whose users make worse decisions
than they would with no model at all.

---

*Sources checked while writing this document:
`Astra/astra-rs/astra-plugin-manifest/src/permissions.rs`;
`Astra/astra-rs/astra-daemon/src/plugins/host_service.rs`
(`HOST_RPC_PERMISSIONS`, `decide_grants`, `ceiling_for`, `declared_permissions`,
`resolve_grants`, `TeardownReason`);
`Astra/astra-rs/astra-daemon/src/plugins/manager.rs` (`InstallOptions::consent`,
`ceiling_admits`, `granted_and_admitted`, `UpdateGate`, `block_codes`);
`Astra/astra-rs/astra-daemon/src/plugins/trust.rs` (`permissions_hash`,
`permission_names`, `Tier`, `TrustRecord`);
`astra-plugin-cli/src/bundle.rs` (`canonical_permissions`, `permissions_hash`);
`astra-registry/schema/version-v1.json`; `astra-registry/bot/lib/bundle.mjs`;
`testdata/bundles/vectors.json`.*

# Versioning and deprecation policy

What the numbers mean, how long a thing you depend on is guaranteed to keep
working, and where that guarantee is written down as data rather than as a
promise somebody has to remember.

## Four numbers, and only one of them is the SDK's

| Number | Where it lives | What it tells you |
| --- | --- | --- |
| **SDK version** | `astra-plugin-sdk/Cargo.toml`, `astra-plugin-sdk-python/pyproject.toml`, `astra-plugin-sdk-ts/package.json` | The authoring API you write against. Each package keeps its own. |
| **Release train** | the `sdk-v<VERSION>` git tag | One tag publishes all three SDKs at once. It names the **Rust crate's** version. |
| **Protocol version** | `proto/PROTO_VERSION` (`protocol=1`), mirrored as `PROTOCOL_VERSION` in every SDK | The wire contract between a plugin and the daemon. |
| **Your plugin's version** | your `plugin.toml` | Yours. The registry orders releases by it. |

The three SDK versions are deliberately not kept equal. The current train is
`sdk-v0.6.0`, and it publishes:

| Package | Registry | Version |
| --- | --- | --- |
| `astra-plugin-sdk` (Rust) | crates.io | 0.6.0 |
| `astra-plugin-macros` | crates.io | 0.6.0 — published **before** the SDK, which depends on it by version |
| `astra-plugin-sdk` (Python) | PyPI | 0.5.0 |
| `astra-plugin-sdk` (TypeScript) | npm | 0.5.0 |

A version number answers "what API am I writing against", so a package that has
had fewer breaking releases has a smaller number. What the train guarantees is
that packages sharing a tag speak the **same protocol** and implement the same
hooks — that is what `spec/hooks.yaml` and the parity checker are for.

## SemVer, at 0.x

All three packages are below 1.0, and follow SemVer's 0.x reading:

- **minor** (`0.5 → 0.6`) — may break source compatibility. Read the CHANGELOG.
- **patch** (`0.6.0 → 0.6.1`) — bug fixes and additions only. If a patch release
  makes your plugin stop compiling, that is a bug in the SDK; file it.

The protocol version is separate and moves on its own. It is an integer, not
SemVer, and the rule for it is not "read the changelog" but a mechanism:

- A hook the peer does not have answers `UNIMPLEMENTED`, which the protocol
  defines as *absent*. The daemon reads it that way and carries on. This is why
  a newer plugin runs against an older daemon and vice versa.
- `MIN_SUPPORTED_DAEMON_PROTOCOL` in each SDK is the oldest daemon that SDK will
  register with. Below it, the plugin exits with a sentence naming the fix
  rather than failing on the first call.

## The deprecation policy

When something in the authoring API is going away:

1. **It is deprecated for at least two minors and at least one calendar
   quarter**, whichever is longer. Deprecated in 0.6 means removable in 0.8, and
   not before three months have passed. A plugin that builds today keeps
   building across at least one release you can plan for.
2. **The deprecation note names the replacement.** Not "deprecated", not
   "use the new API" — the actual identifier you should type instead, or the
   words *no replacement* and why there is none. A deprecation that tells you to
   stop without telling you where to go sends you to the issue tracker.
3. **Removals go under a `BREAKING` heading in the CHANGELOG**, in the package
   that removed it, naming what was removed and what replaced it. Nothing is
   removed in a patch release.

What "deprecated" looks like in each language:

| | How it is marked | What you see |
| --- | --- | --- |
| Rust | `#[deprecated(since = "0.6.0", note = "…")]` | a compiler warning at the use site, with the note |
| Python | `DeprecationWarning` at the call site | `python -W error::DeprecationWarning` turns it into a failure you can gate CI on |
| TypeScript | `/** @deprecated … */` | a strikethrough in your editor and a note in the hover |

A deprecation is a warning, never an error. If a release makes deprecated code
*stop compiling*, that is a removal, and removals follow rule 3.

### What is deprecated right now

| What | Deprecated in | Removed in | Replacement |
| --- | --- | --- | --- |
| Rust: the whole 0.5 trait surface, as `astra_plugin_sdk::compat` | 0.6.0 | 0.8.0 | `PluginCapability` (0.6): `&PluginContext`, `Result<_, ToolError>`, `type Config`. See [migration-0.6.md](migration-0.6.md) |
| Rust: `PluginCapability::source_id()` | 0.6.0 | 0.8.0 | Pass the id to `Host::send_chat_message`; the daemon stopped filtering by source id |
| Rust: `compat::ToolResult` / `ActionResult` / `UiCallResult` | 0.6.0 | 0.8.0 | `Result<String, ToolError>` |
| Rust: `compat::HostClient` / `DaemonClient` aliases | 0.6.0 | 0.8.0 | `ctx.host()` / `ctx.daemon()` |
| Python: a `dict` where a capability dataclass is expected | 0.5.0 | 0.7.0 | The dataclass — `VoiceInfo`, `ToolDef`, … — or its `to_proto()` |
| TypeScript: the `UiPanel` type alias | 0.5.0 | 0.7.0 | `UiContribution` |
| Hook: `AiGetModels` | 0.6.0 | 0.8.0 | No replacement — nothing in the daemon asks a plugin what models it has |

Two footnotes, because both are the kind of thing this policy exists to prevent:

- The Python `DeprecationWarning` for dicts says they are accepted "for one more
  minor release". The **table is the binding number**: two minors and one
  quarter, so 0.7.0 at the earliest.
- `UiPanel` was deprecated in TypeScript with no version recorded at all. It is
  dated 0.5.0 here — the first release that says so in writing — and removable
  from 0.7.0.

## The policy is data

Rules that live only in a document get forgotten at exactly the moment they
matter: the release where somebody deletes the thing. So the per-hook half of
the policy is a column in [`spec/hooks.yaml`](../../spec/hooks.yaml):

<!-- doctest: illustrative reason="one row of spec/hooks.yaml, quoted; the file it belongs to is the source of truth and is checked by tools/parity/check.py" -->
```yaml
  - rpc: AiGetModels
    ...
    routing: deprecated
    deprecated_in: "0.6"
    removed_in: "0.8"
    note: "… Deprecated in 0.6, removed in 0.8, and there is no replacement: nothing in the daemon asks a plugin what models it has, and AiComplete carries the chosen model on the request."
```

`tools/parity/spec.py` validates that on every parse — which means on every
`gen.py` run, every `check.py` run, and therefore on every CI run:

| Rule | The failure it prevents |
| --- | --- |
| `routing: deprecated` requires `deprecated_in` | a hook that has been "deprecated" for years with no date attached |
| `deprecated_in` requires `removed_in` | a deprecation with no end, which is just a rude comment |
| `removed_in` ≥ `deprecated_in` + 2 minors | a removal that lands before anybody had a release to migrate in |
| a deprecated row's `note` names another rpc, or says `no replacement` | "deprecated" with no forwarding address |

Get one wrong and the checker says so, with the line number:

<!-- doctest: output from="python3 tools/parity/check.py on a row whose removed_in violates the policy" -->
```
spec/hooks.yaml is malformed:
  hooks.yaml:336: `AiGetModels` is deprecated in 0.6 and removed in 0.7 — the policy is
  2 minors and one quarter minimum, so the earliest removal is 0.8
```

The versions in those columns are **SDK minors**, not protocol versions: `0.6`
is the number in your `Cargo.toml` and the number the CHANGELOG heading is filed
under. The one-quarter half of the policy is calendar rather than data — the
release train dates it, and this document is where it is written down.

## What is not covered by any of this

- **The daemon's own behaviour.** Astra's UI, its config layout and its internal
  services are not a plugin API. What a plugin may rely on is the protocol, the
  hooks in `spec/hooks.yaml`, and the permissions in its manifest.
- **Anything marked `#[doc(hidden)]`, `_private`, or exported for the test
  harness.** It can change in a patch.
- **`unrouted` hooks.** A hook can exist in the proto and in all three SDKs and
  have no daemon call site — `TtsSynthesizeStream` is one today. Implementing it
  is safe and costs nothing; *depending* on the daemon calling it is not
  supported until its `routing:` says `live`.

## If a deprecation window is not enough

Say so before it closes. A removal that has landed is a removal; a removal that
is still a `removed_in` in `spec/hooks.yaml` is a date, and dates can move if
somebody says why in time.

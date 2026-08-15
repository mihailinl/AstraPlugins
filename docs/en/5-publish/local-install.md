# Installing a local `.astraplugin` file

**Advanced, and it costs you four permissions.** This page describes importing a
bundle that arrived out of band — a colleague sent it, you built it yourself, a
release is not listed yet. It is not how plugins are installed;
[that is the store](get-listed.md), where the artifact is pinned by digest and
verification failures are hard blocks.

> **Handing someone this file is not publishing your plugin.** A bundle you
> built and sent carries no build attestation and no registry record, so it
> installs at a reduced tier on the one machine you sent it to and reaches
> nobody else. Publishing is a tagged release that CI builds and attests, plus
> one listing request — [the whole journey is one page](../publishing.md).

## What it is

`PluginService.ImportPluginFile` takes a **path to a `.astraplugin` file** —
not the bytes, and not a directory. Astra's UI calls it when you pick a file.

The bundle is a ZIP with `MANIFEST.json` as its first, stored entry. The daemon
re-derives every digest, checks the file list is exhaustive in both directions,
and rejects anything that does not match. `astra-plugin verify` runs the same
checks locally, and you should run it before you import a file someone sent you
([install the CLI](../install-cli.md) if you do not have it):

<!-- doctest: cli -->
```bash
astra-plugin verify some-plugin-0.3.0-linux-x64.astraplugin
```

## The ceiling: four permissions are refused outright

An imported file has no catalogue record, so nothing countersigned its bytes and
nothing pinned its author. It installs at **tier 2**, and the tier's ceiling is
not a warning — the permissions are **dropped**:

| Refused, whatever the manifest asks for | Why |
|---|---|
| `send_chat_message` | Drives an AI turn as though the user had spoken |
| `set_theme_contribution` | Restyles the whole app |
| `dom_access` | Runs the plugin's code inside the Astra window |
| `client` | Becomes a chat front-end with its own session |

`fire_trigger`, `subscribe_events`, `set_variable` and `push_to_ui` survive the
ceiling — they are the **low-risk** end of the vocabulary, which is why letting
them through does not need a listing to vouch for them. Of the four, only
`push_to_ui` gets a consent checkbox of its own.

The two lists are deliberately different, and it is worth being precise about
which is which:

| List | Members | What it decides |
|---|---|---|
| `HIGH_RISK_PERMISSIONS` | `send_chat_message`, `push_to_ui`, `set_theme_contribution`, `dom_access`, `client` | each gets its **own consent checkbox**, on every install path |
| `TIER2_REFUSED_PERMISSIONS` | `send_chat_message`, `set_theme_contribution`, `dom_access`, `client` | **dropped outright** from a hand-imported file, consent or not |

They differ by exactly one id: `push_to_ui` is worth a checkbox and is not worth
refusing a file the user deliberately chose to import — it pushes events into
the plugin's own panels and nowhere else. Both lists are in
`astra-plugin-manifest/src/permissions.rs`, which is where the daemon, the CLI
and the registry all read them from, so no third list can drift into existence.

A plugin that needs one of the refused four cannot be delivered this way. It can
be [sideloaded during development](sideload.md), or listed.

## Consent, before anything is written

`InspectPluginFile` reads the manifest **without installing**: nothing is
extracted, nothing starts, no trust record is written, no bytes are copied out
of the archive. The file is parsed in memory and closed. Calling it and then
never importing leaves the machine exactly as it was.

That is what lets Astra show you the same permission sheet the store path shows
before you commit to anything.

## What you give up compared to the store

| | Store | Imported file |
|---|---|---|
| Bytes countersigned by the registry | yes | no |
| Author pinned, so an update from a different repo is refused | yes | no |
| Withdrawal (revocation) reaches you | yes (once the chain is anchored) | no |
| Updates | automatic, with a permission-change review | you find the next file yourself |
| High-risk permissions | available, with consent | **four are refused** |
| Verification failure | hard block, no override | the archive checks still apply |

The plan describes promoting an imported file to full trust when its digest
turns up in a fresh index. **That promotion is not implemented** — an import
stays tier 2 for its lifetime.

## Before you import something someone sent you

A plugin is a native process with your full user privileges. There is no
sandbox. Importing a file is a decision about the person who sent it, not about
the file. [The security model](../1-orientation/security.md) says what the
mechanisms do and do not prove.

If it is your own plugin and you are still writing it, you want
[`astra-plugin dev`](sideload.md), not this.

# Astra plugin documentation

A plugin is a separate program that Astra starts and talks to over gRPC. It can
give the model tools, provide a text-to-speech or speech-to-text engine, add
steps and triggers to the command editor, contribute UI, or act as a chat client
of its own.

There are two journeys here, and everything on this page belongs to one of them.

## Writing a plugin

| | |
|---|---|
| [What a plugin is](1-orientation/what-is-a-plugin.md) | The ten capabilities, and which one you want |
| [Architecture](1-orientation/architecture.md) | Process model, the two services, the auth handshake |
| [Security model](1-orientation/security.md) | What signatures prove, what they do not, and the privilege a plugin runs with |
| [Platforms](1-orientation/platforms.md) | linux-x64 and windows-x64, per-OS paths, build prerequisites |
| **[Getting started](2-tutorial/getting-started.md)** | **Zero to a running plugin. Start here.** |
| [Rust SDK](4-sdk/rust.md) · [Python SDK](4-sdk/python.md) · [TypeScript SDK](4-sdk/typescript.md) | One page each, including what that SDK cannot do yet |
| [Examples](7-examples/README.md) | Eleven plugins in this repository, each with its platform |

## Publishing a plugin

The canonical path, and the only one users see:

1. [Release with CI](5-publish/release-with-ci.md) — `astra-plugin init-ci`, then a tag. GitHub builds and attests the bundle.
2. [Get listed](5-publish/get-listed.md) — one submission, once, ever. After that, releases are zero-touch.
3. Users install from inside Astra, with the artifact pinned by digest.

Two other ways to get a plugin onto a machine exist. Both are for developers,
both cost something, and both say what:

- [Install a local file](5-publish/local-install.md) — a `.astraplugin` received out of band. Four permissions are refused outright.
- [Sideload a source directory](5-publish/sideload.md) — the authoring loop. Requires Developer Mode, runs unsigned code with your full user account.

Also: [versioning and deprecation policy](versioning.md) · [migrating to 0.6](migration-0.6.md)

## Running one

| | |
|---|---|
| [Troubleshooting](6-operate/troubleshooting.md) | Keyed to the errors the daemon and the CLI actually print |
| [Logs](6-operate/logs.md) | Where they are, per OS, and how to follow them |
| [Performance](6-operate/performance.md) | Timeouts, start budget, shutdown grace, archive limits |

## Reference

Most of the reference tier is **generated** from the code it describes, and CI
fails when a checked-in page differs from a fresh run. That is deliberate: a
reference page that is written by hand is a second definition of the interface,
and it is always the one that is wrong.

| Page | Generated from |
|---|---|
| [`plugin.toml`](reference/manifest.md) | `astra-plugin-manifest` — the crate the daemon parses your manifest with |
| [CLI](reference/cli.md) | the `clap` definitions, by running `astra-plugin --help` |
| [Protocol](reference/protocol.md) | `proto/plugin.proto` |
| [Errors](reference/errors.md) | the error taxonomy in all three SDKs |
| [Hook parity](reference/parity.md) | `spec/hooks.yaml` — all 35 hooks in all three SDKs |
| [Permissions](3-reference/permissions.md) | written: each permission, what it grants, how to write a reason |
| [Config fields](3-reference/config-fields.md) | written: settings UI, `[config]`, and the TTS/STT field hooks |

Normative specifications, for someone implementing a verifier or a registry
rather than a plugin: [bundle v2](spec/bundle-v2.md) ·
[registry index](spec/registry-index.md) · [permissions](spec/permissions.md).

## Languages

English is authoritative. [Русский](../ru/README.md) covers the written pages
and is reviewed. Five older translations — `de`, `es`, `ja`, `uk`, `zh-CN` —
are in [`docs/community/`](../community/), last synchronised 2026-04-17, behind
a banner saying so. They are not current and are not maintained; corrections
are welcome anyway.

## Two things the whole of this documentation is careful about

**Plugins are not sandboxed.** A plugin is a native process running as you, with
your files and your network. Signatures answer *who published these bytes*;
permissions answer *what the daemon will do when the plugin asks*. Neither
answers what the process can do to your machine. See
[the security model](1-orientation/security.md).

**The trust chain is specified and not yet anchored.** The root keys exist and
match on both sides; the root-signed `trust.json` that delegates to an
index-signing key does not, so a default build has nothing to check a catalogue
signature against, fails closed, and classifies every catalogue as unsigned.
This is written down in [`spec/registry-index.md` §0.1](spec/registry-index.md)
and repeated wherever it matters, rather than being quietly implied away.

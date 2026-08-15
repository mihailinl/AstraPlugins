# Getting started

Zero to a plugin that rolls dice, has tests, and is packaged for release. About
fifteen minutes, most of it waiting for `cargo`.

Every code block on this page is executed by
[`docs/tools/doctest.py`](../../tools/doctest.py) in CI. If one of them is wrong,
the build is red before you read it.

## 1 · Install the CLI

One line. It takes a few minutes and ends by printing a version.

<!-- doctest: cli -->
```bash
cargo install --git https://github.com/mihailinl/AstraPlugins astra-plugin-cli --locked
astra-plugin --version
```

<!-- doctest: output from="astra-plugin --version" -->
```
astra-plugin <version>
```

The number is a placeholder on purpose: `--git` builds whatever commit `master`
carries when you run it, so what prints is that commit's version rather than one
you chose.

From a clone, `cargo install --path astra-plugin-cli --locked` does the same.

**You need Rust 1.85 or newer and `protoc` on your PATH.** Without `protoc` the
build stops at ``Could not find `protoc` ``. Install it with `apt install
protobuf-compiler`, `pacman -S protobuf`, `brew install protobuf`, or `winget
install Google.Protobuf`, then run the line again.

**A version number cannot tell you this build is good, and a `0.2.0` is not a
bad one.** `init-ci` used to pin a tag *object* where GitHub needs a commit, and
a plugin's first `git push --tags` died on it. The fix is commit `5b8ab22`,
which landed on `master` *before* the bump that raised the number to `0.2.1` —
so a build from `master` can carry the fix and still print `0.2.0`, and no
`0.2.1` build exists without it. Installing from `master` today gets you the fix
whatever the number says; to check rather than trust, run `astra-plugin init-ci`
and read the pin it prints — `e3329df252a46d747676cb540ae4b986af68a3ad` is the
commit and is right, `dc1a044876926e9cf1170f034e2eab533ec07641` is the tag
object and is the bug. Long version:
[Install the CLI](../install-cli.md#the-bug-that-breaks-a-first-release-and-how-to-tell-whether-your-build-has-the-fix).

One aside, which does not block you: the CLI is not on crates.io and has no
prebuilt binaries, so building it is the only way to get it. Prebuilt binaries
are planned. Full detail, including what to do when it does not work:
[Install the CLI](../install-cli.md).

Check the machine before you blame the code:

<!-- doctest: cli -->
```bash
astra-plugin doctor
```

It answers sixteen questions in one pass — which CLI you are running, which
config directory it resolved, whether Astra is reachable, which toolchains you
have (`protoc` included), and whether your release workflow is pinned. It is the
first thing to run when anything is confusing.

## 2 · Scaffold

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang rust --template tool
cd dice-roller
```

<!-- doctest: output from="astra-plugin new dice-roller --lang rust --template tool" unrun="creates a directory tree; re-run it in an empty directory of your own" -->
```
Created plugin project 'dice-roller' at dice-roller/
Language: rust
Template: tool
Capabilities: tools

Next steps:
  cd dice-roller
  cargo build --release
  astra-plugin test .
  astra-plugin dev .
```

Six files:

<!-- doctest: illustrative reason="an annotated tree of what `astra-plugin new` wrote, not a command; the run that produced it is the output block above" -->
```
dice-roller/
├── plugin.toml      the manifest — id, version, capabilities, entry point
├── Cargo.toml       one dependency, and a long comment explaining why only one
├── src/main.rs      the plugin: fifteen lines, plus a test module
├── README.md        what the store shows next to your plugin
├── icon.svg         a placeholder icon, meant to be replaced
└── .gitignore       `target/` and `*.astraplugin`
```

`README.md` and `icon.svg` are not decoration: the packer picks both up by name,
and the registry reads them back out of the verified bundle to build your
listing's card and page. They are what a person sees before deciding to install
you, so replace them before you publish —
[Get listed](../5-publish/get-listed.md) says what each one wants.

`--lang` takes `rust`, `python` or `typescript`; `--template` picks the
capabilities and the example code, and `--capabilities tools,triggers` overrides
whatever the template implies.

### What the scaffold pins

| Language | The scaffold pins | Published |
|---|---|---|
| Rust | `astra-plugin-sdk = "0.6"` | crates.io 0.6.0 |
| Python | `astra-plugin-sdk>=0.5,<0.6` | PyPI 0.5.0 |
| TypeScript | `"astra-plugin-sdk": "^0.5.0"` | npm 0.5.0 |

Those resolve from the registries, so `cargo build`, `pip install -r
requirements.txt` and `bun install` work in a fresh project with nothing to
configure.

**The lower bounds are load-bearing.** Rust 0.6 is the first release whose
`HostClient` attaches `x-session-token`, and Python and TypeScript 0.5.0 are
theirs; against anything older the daemon answers `unauthenticated` on every
host call. Relaxing a bound trades a resolver error for a runtime one, which is
the worse trade — the plugin starts, serves hooks, and silently cannot talk back.

Python: `astra-plugin test` runs your plugin with whatever `python` is on
`PATH`, so activate the virtualenv you installed into first. Otherwise the
plugin exits with `ModuleNotFoundError: astra_plugin_sdk` before it registers.

## 3 · Write the plugin

Replace `src/main.rs` with this. It is the whole plugin — typed arguments, a
tool, a trigger, and three tests.

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;

/// The arguments the model sends. The doc comments become the JSON Schema it
/// reads, so write them for a reader who has never seen this plugin.
#[astra::args]
struct Roll {
    /// How many dice to roll
    #[serde(default = "one")]
    count: u32,
    /// How many sides each die has
    #[serde(default = "six")]
    sides: u32,
}

fn one() -> u32 { 1 }
fn six() -> u32 { 6 }

#[derive(Default)]
struct DiceRoller;

#[astra::plugin]
impl DiceRoller {
    /// Roll dice and return the total. Use it whenever the user asks for a
    /// random number, a dice roll, or a coin flip.
    #[tool]
    async fn roll_dice(&self, ctx: &PluginContext, a: Roll) -> Result<String, ToolError> {
        if a.sides < 2 {
            return Err(ToolError::BadArguments("a die needs at least 2 sides".into()));
        }
        let total: u32 = (0..a.count).map(|_| 1 + rand_below(a.sides)).sum();
        ctx.host()
            .fire_trigger("dice_rolled", &json!({ "total": total }).to_string())
            .await?;
        Ok(total.to_string())
    }
}

/// Not a dependency: `SystemTime` is enough entropy for a dice roll.
fn rand_below(n: u32) -> u32 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().subsec_nanos();
    nanos % n
}

astra::main!(DiceRoller::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn it_rolls_and_fires_the_trigger() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();

        let total: u32 = h
            .call_tool("roll_dice", json!({ "count": 3, "sides": 6 }))
            .await
            .expect("the tool answered")
            .parse()
            .unwrap();
        assert!((3..=18).contains(&total), "three d6 cannot total {total}");

        assert_eq!(h.fired_triggers().len(), 1);
        assert_eq!(h.fired_triggers()[0].trigger_type, "dice_rolled");
    }

    #[tokio::test]
    async fn a_one_sided_die_is_rejected() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        let err = h
            .call_tool("roll_dice", json!({ "sides": 1 }))
            .await
            .expect_err("a die needs two sides");
        assert!(err.to_string().contains("2 sides"), "{err}");
    }

    /// What the user sees if they never granted `fire_trigger`.
    #[tokio::test]
    async fn a_denied_permission_surfaces_as_an_error() {
        let h = Harness::new(DiceRoller::default()).start().await.unwrap();
        h.host().deny("fire_trigger");
        let err = h.call_tool("roll_dice", json!({})).await.expect_err("denied");
        assert!(err.to_string().contains("fire_trigger"), "{err}");
    }
}
```

Five things are worth naming:

- **`#[astra::args]`, not `#[derive(Deserialize, JsonSchema)]`.** serde's derive
  emits `extern crate serde`, which resolves through the extern prelude and
  cannot be reached through a re-export — so the plain derive would need `serde`
  in *your* `Cargo.toml`, which is the one thing the scaffold promises you do
  not need. `#[astra::args]` is those two derives pointed at the SDK's copies.
- **The doc comment is the description the model reads.** Both on the tool and
  on each field. Say when to use the tool, not how it works.
- **Handlers return `Result<_, ToolError>`.** A per-call failure is *data*: the
  AI loop reads it and decides what to do, so it travels in the response rather
  than as a gRPC status. `?` works on `serde_json::Error`, `std::io::Error`,
  `tonic::Status` and `anyhow::Error`.
- **`ctx.host()` is always there.** The context carries the host client, the UI
  language and the live trigger set; it is cheap to clone into a background
  task and is never `None`. Nothing goes on your struct behind a lock.
- **`h.host().deny("fire_trigger")` stages a refusal.** That is what a user who
  did not consent looks like, and it is worth a test — it is the failure your
  issue tracker will otherwise receive.

`cargo test` runs those three against a recording host: no daemon, no socket,
no Astra installed.

<!-- doctest: illustrative reason="the block above carries test=1, so the doc-test already ran cargo test on it" -->
```bash
cargo test
```

## 4 · Declare what you need

The tool calls `fire_trigger`, and `[permissions]` is default-deny, so it has to
ask. The `reason` is what the user reads when Astra asks them to consent —
write it as a sentence about *your plugin*, not about the permission.

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "dice-roller"
name = "Dice Roller"
version = "0.1.0"
description = "Roll dice from chat, and fire a trigger with the result."
author = "Your Name"
license = "MIT"
homepage = "https://github.com/you/dice-roller"

[entry]
command = "target/release/dice_roller"

[capabilities]
tools = true
triggers = true

[permissions]
fire_trigger = { reason = "Fires the trigger you configure when a roll completes" }
```

Then check it:

<!-- doctest: cli -->
```bash
astra-plugin check --strict
astra-plugin check --fix
```

`check` reads the manifest with the daemon's own parser — the same crate,
vendored and held byte-identical — so it cannot disagree with what will happen
at install time. `--fix` applies the corrections it can prove and reports the
rest.

## 5 · Run the conformance suite

<!-- doctest: cli -->
```bash
astra-plugin test
```

This is a level above `cargo test`: it starts your plugin the way the daemon
starts it, against a mock daemon serving `PluginHostService`, and calls every
inbound hook your declared capabilities imply.

<!-- doctest: output from="astra-plugin test . --no-build, in the dice-roller project this page builds (the plugin's own tracing lines, which go to stderr, are left out)" unrun="starts a real plugin process and runs the conformance suite against it; needs a built plugin" -->
```
  [ok  ] ListTools                required  1 tool(s)
  [ok  ] GetPluginTriggerTypes    required  0 trigger type(s)
  [ok  ] CallTool                 required  `roll_dice` answered
  [ok  ] OnActiveTriggers         optional  accepted 0 active trigger(s)
  [ok  ] OnConfigChanged          optional  accepted
  [ok  ] OnLanguageChanged        optional  accepted
  [ok  ] HealthCheck              required  healthy = true, status = ok
  [ok  ] Shutdown                 required  acknowledged in 40.8ms
  [ok  ] the plugin says something before the daemon gives up: first line on stdout after 775.4µs (the daemon waits 20s, spec/limits.yaml plugin_start_timeout_secs)
  [ok  ] tool schemas parse with an object root: 1 tool schema(s) checked
  [ok  ] config schema parses with an object root: no [config] section — nothing to check
  [ok  ] Shutdown is honoured within the grace period: the process exited 40.8ms after Shutdown (grace is 5s, spec/limits.yaml plugin_stop_grace_secs)
  [ok  ] the plugin talked to the daemon: 2 host call(s) reached the daemon: fire_trigger, log
  [ok  ] every host call carried the session token: no host call was refused for want of `x-session-token`

  OK: 8 hook(s) exercised, 6 check(s) passed.
```

`GetPluginTriggerTypes` reports **0** even though the plugin fires a trigger.
Firing one and *offering* one are different things: the command editor lists
what the plugin declares, which is a `#[hook] async fn trigger_types(&self) ->
Vec<TriggerTypeDef>`, and the plugin above has none. Scaffolding with
`--capabilities tools,triggers` writes that hook for you; §3 left it out to keep
the file to one screen. Fire without declaring and the trigger still fires —
but nobody can wire a command to it.

A `required` hook may not answer `UNIMPLEMENTED`; an `optional` one may, because
on the wire `UNIMPLEMENTED` *means* "this hook is absent".

## 6 · Run it inside Astra

This step needs a running Astra and **Developer Mode**, because it sideloads an
unsigned directory:

<!-- doctest: cli -->
```bash
astra-plugin dev
```

It runs `check --strict`, builds, hands the directory to the daemon — which
spawns the process, mints its token and owns its lifecycle — then watches for
changes, rebuilds, restarts and tails the logs.

Read [sideloading](../5-publish/sideload.md) before you turn Developer Mode on.
It is a developer tool: it runs unsigned local code with your full user
privileges, and the switch lowers the bar for every plugin on the machine, not
just this one. It is not how anyone installs a plugin.

If `dev` cannot reach Astra, `astra-plugin doctor` tells you which of the two
things is wrong — the daemon is not running, or it resolved a different config
directory than the CLI did.

## 7 · Package

<!-- doctest: cli -->
```bash
astra-plugin build
astra-plugin verify dice-roller-0.1.0-linux-x64.astraplugin
```

<!-- doctest: output from="astra-plugin build ., in the dice-roller project this page builds (the size and the two digests are properties of your build, not constants)" unrun="needs a scaffolded, compiled plugin on disk; re-run it in the project this page builds" -->
```
Building plugin 'dice-roller' v0.1.0 (rust) for linux-x64...
  Running cargo build --release...
    Finished `release` profile [optimized] target(s) in 0.04s
  Added: README.md (0644)
  Added: bin/dice_roller (0755)
  Added: plugin.toml (0644)
  Built: dice-roller-0.1.0-linux-x64.astraplugin (2757.1 KB, 3 files)
  target:          linux-x64
  artifact sha256: 3ae95e05f49156b137afe4b528dc1feb4df4c36c5e8c284b52b7b15e4f3345fa
  manifest digest: 11b1b78dd55232877c881e862e109ec594aa535167d27063a2e3fcbe373d9824
  Unsigned. Local keys are not a trust signal in Astra — trust comes from the registry.
  See https://github.com/mihailinl/AstraPlugins/blob/master/docs/en/publishing.md#what-establishes-trust
```

`verify` re-reads what `build` just wrote and answers a different question: that
`MANIFEST.json` is entry 0 and stored, that the file list is exhaustive in both
directions, and that every listed digest, size and mode matches the archive. It
says nothing about who wrote it — that is the registry's job.

The file name is not cosmetic: `<id>-<version>-<target>.astraplugin` is the name
a published bundle must have, and the target segment is the registry's platform
key.

**`build` does not sign, and you do not need a key.** What makes Astra install a
plugin is a registry record countersigning the sha256 of the whole file — not
any key you hold. See [the security model](../1-orientation/security.md).

## 8 · Publish

Now the part that matters, and it is two commands:

<!-- doctest: cli -->
```bash
astra-plugin init-ci
astra-plugin version 0.1.1
```

`init-ci` writes `.github/workflows/release.yml`, pinned by commit SHA to
Astra's reusable release workflow. After that, **a tag is the whole release
process**: CI builds every target, attests each bundle with GitHub's build
provenance, and attaches them to a GitHub Release.

Then one submission, once ever, and every later release is zero-touch.

Note what publishing is **not**: pushing this repository to GitHub does not
publish your plugin, and neither does sending someone the `.astraplugin` you
just built. The registry pins the digest of a file CI produced and reads the
build attestation attached to it, and a file built on your laptop carries
neither.

**→ [Publishing a plugin](../publishing.md)** — the whole journey in one page,
from here to a listed plugin, with every command and its expected output. The
tier pages behind it: [Release with CI](../5-publish/release-with-ci.md) ·
[Get listed](../5-publish/get-listed.md)

## The same thing in Python

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang python --template tool
```

<!-- doctest: python-plugin -->
```python
"""DiceRoller — an Astra plugin."""

from astra_plugin_sdk import Plugin, tool


class DiceRoller(Plugin):
    """Roll dice from chat."""

    @tool("Roll dice and return the total.")
    async def roll_dice(self, count: int = 1, sides: int = 6) -> str:
        # The parameters ARE the schema: a parameter with no default is
        # required, one with a default is optional, and the type hints become
        # the JSON types the model is shown.
        if sides < 2:
            raise ValueError("a die needs at least 2 sides")
        total = sum(1 + (i % sides) for i in range(count))
        await self.host.fire_trigger("dice_rolled", f'{{"total": {total}}}')
        return str(total)


if __name__ == "__main__":
    DiceRoller().run()
```

The entry point is `[entry] command = "python"`, `args = ["-m", "src.plugin"]`,
`runtimes = ["python"]`, and the bundle is `noarch`.

## The same thing in TypeScript

<!-- doctest: cli -->
```bash
astra-plugin new dice-roller --lang typescript --template tool
```

<!-- doctest: ts-plugin -->
```typescript
import { plugin, s, tool } from "astra-plugin-sdk";

export const app = plugin({
  tools: {
    roll_dice: tool({
      description: "Roll dice and return the total.",
      // Declared once: this is the JSON Schema the model is shown AND the type
      // of `run`'s first argument. The SDK validates the model's arguments
      // against it before your code runs.
      input: s.object({
        count: s.number({ description: "How many dice to roll" }).optional(),
        sides: s.number({ description: "How many sides each die has" }).optional(),
      }),
      run: ({ count, sides }) => {
        const n = count ?? 1;
        const faces = sides ?? 6;
        if (faces < 2) throw new Error("a die needs at least 2 sides");
        let total = 0;
        for (let i = 0; i < n; i++) total += 1 + Math.floor(Math.random() * faces);
        return String(total);
      },
    }),
  },
});

// `astra-plugin build` bundles this to CommonJS, so `require.main` is the
// honest "am I the entrypoint" test. Importing this module — as a test does —
// does not start a server.
if (require.main === module) app.run();
```

## Where to go next

| If you want | Read |
|---|---|
| The whole Rust API | [Rust SDK](../4-sdk/rust.md) |
| Every `plugin.toml` key | [manifest reference](../reference/manifest.md) |
| Every hook, in every SDK | [parity](../reference/parity.md) |
| To ship it | [Release with CI](../5-publish/release-with-ci.md) |
| Something is broken | [Troubleshooting](../6-operate/troubleshooting.md) |
| A worked example | [Examples](../7-examples/README.md) — eleven of them |

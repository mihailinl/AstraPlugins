# Sideloading — a developer tool

> **This is not how a plugin is installed.** Sideloading points Astra at a
> source directory on your disk and runs it, unsigned, as a native process with
> your full user account's privileges. It exists so that you can develop a
> plugin. It is behind an explicit opt-in, and the opt-in lowers the bar for
> **every** plugin on the machine, not just yours.
>
> Users install from inside Astra. Authors publish with
> [`init-ci` and a tag](release-with-ci.md) and then
> [get listed once](get-listed.md) — [the whole journey is one
> page](../publishing.md).
>
> Telling someone to clone your repository and sideload it is not publishing.
> It asks them to run unsigned code as themselves, and it reaches exactly the
> people you can talk to.

Never sideload a plugin you did not write or audit. If someone sends you a
directory and instructions to turn on Developer Mode, they are asking you to run
their code as yourself.

## Turning it on

Sideloading is refused unless `safety.allow_unsigned_plugins` is true. The
daemon says so in exactly those terms:

<!-- doctest: illustrative reason="the daemon's refusal, quoted from astra-daemon/src/plugins/manager.rs; reproducing it needs a running Astra with the setting off" -->
```
Sideloading is disabled. It runs an unsigned local plugin as native code with
your full privileges. Turn on Settings -> Privacy -> "Allow unsigned plugins"
(`safety.allow_unsigned_plugins`) to sideload (local plugin development only).
```

and the CLI turns that into the same instruction with the fix on its own line
(`astra-plugin-cli/src/daemon.rs`). The two messages name different sections of
Settings — the daemon says Privacy, the CLI says Safety. The **setting key is
`safety.allow_unsigned_plugins`** and that is the thing to search for.

## Using it

One command, from [the CLI](../install-cli.md):

<!-- doctest: cli -->
```bash
astra-plugin dev
astra-plugin dev . --daemon-addr 127.0.0.1:32000
```

`dev` does four things in order, and stops at the first failure:

1. `astra-plugin check --strict` — it will not hand the daemon a manifest that
   is already wrong;
2. builds;
3. hands the **directory** to the daemon over `SideloadPlugin`, which spawns
   the process, mints its auth token and owns its lifecycle from then on;
4. watches for changes, rebuilds, stop/starts the plugin, and tails its output.

<!-- doctest: output from="astra-plugin dev . with no Astra running" unrun="needs a machine with no Astra daemon listening, which a CI runner cannot promise either way" -->
```
Dev mode: plugin 'dice-roller'
  Directory: /tmp/dice-roller
Checking plugin at /tmp/dice-roller...
  OK: plugin 'dice-roller' v0.1.0 is valid (0 warning(s), 2 note(s), capabilities: tools)
  Running cargo build --release...
    Finished `release` profile [optimized] target(s) in 2.48s
Error: Could not read /home/you/.config/astra/daemon.token. Astra does not look
like it is running — start the app first.
```

**The daemon owns the process, and that is not a style choice.** A plugin
authenticates to `PluginHostService` with a token the daemon mints when it
spawns the process, and the daemon rejects any `Register` that does not carry a
token it issued. A CLI-spawned plugin has no way to get one — the self-spawning
dev loop this replaced started a process that talked to nobody.

`--standalone` keeps that older behaviour for the cases where it is still
useful (checking that a binary starts, driving it by hand) and says up front
that the plugin cannot register with Astra that way.

`dev --json` is refused, deliberately: `--json` promises one document per run
and `dev` never finishes. `astra-plugin check --json`, `astra-plugin test --json`
and `astra-plugin logs --json` are the machine-readable halves of what it does.

## What sideloading costs, precisely

| | |
|---|---|
| **Signature** | none. Nothing vouches for the code |
| **Privileges** | your full user account. There is no sandbox — [Phase 7 does not exist](../1-orientation/security.md) |
| **Blast radius of the switch** | `allow_unsigned_plugins` applies to every plugin on the machine, including unsigned files you import later |
| **Auto-start** | **never.** Developer Mode is required at load time, and a restart leaves a sideloaded plugin stopped until you start it again |
| **Permission ceiling** | **none** — see below |
| **Provenance shown to the user** | tier `sideloaded` — "loaded from a folder" — in the provenance panel |

### Why there is no permission ceiling here

A [locally imported `.astraplugin`](local-install.md) has four permissions
refused outright. A sideloaded **source directory** does not, and the exception
is deliberate rather than an oversight: this is the authoring loop for UI
plugins, and `dom_access` is exactly what `companion`, `doom` and `bad-apple`
need. Capping tier 3 would make those undevelopable.

The trade is that tier 3 is gated by an explicit setting, never auto-starts,
and is a directory you pointed at yourself — three facts that tier 2 (a file
that arrived from somewhere) cannot claim.

The plan also asks for a permanent, non-dismissible "DEVELOPER — unverified
code from a local directory" badge on the plugin card and on the window chrome
whenever `dom_access` is live. **That badge is not in the UI today**, and this
page does not claim it is.

## What does not work, and will not

**Hand-writing a `sideload.json` marker into the plugins directory.** The daemon
refuses a marker it has no record of authorising:

<!-- doctest: illustrative reason="a daemon log line, quoted from astra-daemon/src/plugins/manager.rs; it is emitted on a machine with a planted marker" -->
```
Refusing sideload marker in <path>: this daemon never authorised a sideload of
'<id>' from <source> (no matching record in <registry path>). A marker file
alone does not authorise running unsigned native code.
```

Older instructions told authors to drop a marker into
`~/.config/astra/astra/plugins` — a path that does not exist, on top of a
mechanism that no longer works, without mentioning the `allow_unsigned_plugins`
prerequisite. They have been deleted rather than corrected. The replacement is
one line: `astra-plugin dev`.

## When you are done developing

Nothing about this path produces something another person can install. To ship:

1. [`astra-plugin init-ci`](release-with-ci.md), then a tag — CI builds and
   attests it;
2. [`astra-plugin publish`](get-listed.md) — once, ever;
3. users install it from inside Astra, with the digest pinned.

Turning `allow_unsigned_plugins` back off when you are not developing is worth
the two clicks.

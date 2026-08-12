# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2026 Minice — https://minice.ai

"""Shared numeric limits, generated from spec/limits.yaml.

AUTO-GENERATED — DO NOT EDIT.

Produced by `tools/gen-limits.mjs` from `spec/limits.yaml`.
Regenerate with `node tools/gen-limits.mjs` at the repo root.
These numbers are shared with the Astra daemon; changing one here without
changing the spec is a silent protocol break, which is why this file is
generated and CI re-runs the generator with `--check`.
"""

#: SHA-256 of the ``spec/limits.yaml`` these constants were generated from.
SPEC_SHA256 = "4c2233725bc33d310b28ca4aabec38f7fd6ba6e1cf5970348f8fa5a624ab3d3d"

#: Capacity of the audio channel that carries streaming-STT chunks from the
#: daemon's voice pipeline into the plugin process, in chunks.
#:
#: It bounds TWO channels in series and both must be this value: the daemon's
#: (`SttSession` -> `SttProcess` bridge) and the SDK's (inbound gRPC stream ->
#: the plugin's `stt_transcribe_stream` hook). The smaller of the two is the
#: real capacity, which is how a 32-slot SDK channel silently capped a 500-slot
#: daemon one. 500 is ~10 s of audio: the worst-case wake-word seed dump (~8 s
#: in 100 ms batches) plus live audio arriving while a slow provider is still
#: inferring, with headroom, so a busy provider back-pressures instead of the
#: audio loop dropping chunks.
STT_AUDIO_CHANNEL_CAPACITY = 500

#: How long the daemon waits for a freshly spawned plugin process to produce its
#: first line of output before declaring the start a failure, in seconds.
#: An SDK must reach "ready" — bind its port, print its line — inside this.
PLUGIN_START_TIMEOUT_SECS = 20

#: Grace the daemon gives a plugin's `Shutdown` RPC on a normal stop (user stop
#: / disable / uninstall) before it kills the process group, in seconds.
#: An SDK's own drain budget must not exceed this, or the SDK's tidy path never
#: gets to run: the daemon kills it first. (Daemon shutdown passes a much
#: shorter grace, bounded by the whole-teardown deadline — that path is
#: deliberately not this number.)
PLUGIN_STOP_GRACE_SECS = 5

#: Maximum combined uncompressed size the daemon will extract from one
#: `.astraplugin` archive, in bytes (500 MiB). Zip-bomb mitigation.
#: A packaging tool that produces a bundle over this makes an uninstallable
#: plugin, so the CLI is expected to refuse at build time.
MAX_EXTRACT_BYTES = 524_288_000

#: Maximum number of entries in one `.astraplugin` archive. Zip-bomb
#: mitigation, same contract as `max_extract_bytes`.
MAX_ARCHIVE_ENTRIES = 10_000

#: How long a lease stays redeemable after it is ISSUED, in seconds.
#:
#: A ceiling, not the lifetime: the daemon's own budget for one work RPC is the
#: plugin's declared `plugin.call_timeout_secs`, else 120 s
#: (`astra-daemon/src/plugins/manager.rs:747,781`), and nothing caps what a
#: plugin may declare. So the lifetime is the call's budget plus
#: `lease_fire_grace_secs`, clamped to this. 300 s is 2.5x the default budget: a
#: plugin that declares longer than this is doing work the lease cannot usefully
#: span anyway, and it degrades to a root event rather than failing.
LEASE_TTL_SECS = 300

#: How long a lease stays redeemable after the plugin call RETURNS, in seconds.
#:
#: This window exists because the reference idiom fires from a DETACHED task:
#: `examples/dice-roller/src/main.rs` clones the host out of the context,
#: `tokio::spawn`s, and returns — every fire happens after the RPC is over. So
#: the honest question is not "how long after returning is a fire still
#: plausibly caused by the call" but "how long can that shipped loop take".
#:
#: The answer is bounded by `lease_max_fires` below: up to 100 sequential host
#: RPCs, each a round trip to a daemon that may be busy. 30 s covers the whole
#: loop at 300 ms per fire, which is three orders of magnitude slower than a
#: healthy local call. A stingier value would work on an idle machine and lose
#: attribution on a loaded one, which is the worst way for this to fail.
LEASE_FIRE_GRACE_SECS = 30

#: How many trigger fires ONE lease may redeem, so it cannot be replayed
#: indefinitely.
#:
#: The floor here is measured, not chosen: `dice-roller` clamps its die count to
#: `1..=100` (`main.rs:103,147,157`) and fires `on_roll_value` once per die from
#: a single `roll_dice` call. Anything below 100 silently unattributes the tail
#: of a `100d6` roll — in the very example the whole effort was filed from. 256
#: keeps that whole loop leased with real headroom while still bounding a buggy
#: or hostile plugin's fan-out from one call.
#:
#: It is a replay bound, not a rate limit. Leased fires are deliberately not
#: throttled; root fires are, by a separate token bucket the daemon owns.
LEASE_MAX_FIRES = 256

__all__ = [
    "SPEC_SHA256",
    "STT_AUDIO_CHANNEL_CAPACITY",
    "PLUGIN_START_TIMEOUT_SECS",
    "PLUGIN_STOP_GRACE_SECS",
    "MAX_EXTRACT_BYTES",
    "MAX_ARCHIVE_ENTRIES",
    "LEASE_TTL_SECS",
    "LEASE_FIRE_GRACE_SECS",
    "LEASE_MAX_FIRES",
]

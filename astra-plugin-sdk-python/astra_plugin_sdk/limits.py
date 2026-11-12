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
SPEC_SHA256 = "947a19862bfbe6c189e66ad6699c212e5c2c020ca23d5512ab8a18da4d934501"

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

#: How often an SDK re-sends a music provider's snapshot when nothing changed,
#: in seconds (`PluginCapabilityService.MusicSubscribe`).
#:
#: A snapshot stream that stays open but goes silent — a wedged plugin, a stuck
#: event loop — is otherwise indistinguishable from a quiet one, and the music
#: widget would show a ghost of what played an hour ago. The heartbeat is what
#: lets the daemon tell the two apart: see `music_session_stale_secs`.
MUSIC_SNAPSHOT_HEARTBEAT_SECS = 15

#: How old a music provider's last snapshot may be before the daemon stops
#: believing it, in seconds.
#:
#: Three heartbeats: one lost to a slow event loop is normal, three in a row is a
#: plugin that has stopped reporting. Must stay well above the heartbeat, or a
#: healthy provider's sessions blink out between two of its snapshots.
MUSIC_SESSION_STALE_SECS = 45

#: The most sessions one music snapshot may carry; the daemon drops the rest.
#:
#: A session is one playback a service reports (an account's active device, a
#: browser tab). Sixteen covers every service a plugin could reach many times
#: over; the bound exists so a buggy plugin cannot fill the widget's session
#: switcher or the daemon's memory.
MUSIC_SNAPSHOT_MAX_SESSIONS = 16

#: The most items one music search may return from one provider.
#:
#: The widget shows ten; the AI reads fewer. Twenty leaves room without letting a
#: provider hand back a whole catalogue page per keystroke.
MUSIC_SEARCH_MAX_ITEMS = 20

#: The largest gRPC message either end of the plugin protocol accepts, in bytes
#: (64 MiB). The daemon decodes what a plugin sends up to this
#: (`plugins::client::MAX_PLUGIN_MESSAGE_BYTES`), and every SDK's capability
#: server receives what the daemon sends up to this. Must stay well above
#: `plugin_image_request_max_bytes`: the pictures are not the whole request.
PLUGIN_MAX_MESSAGE_BYTES = 67_108_864

#: The most picture bytes the daemon puts in one `AiComplete` request, in bytes
#: (20 MiB). The newest pictures of the conversation are kept within it, and the
#: message text notes one that was left out
#: (`plugins::capability_bridge::PLUGIN_IMAGE_REQUEST_MAX_BYTES`).
PLUGIN_IMAGE_REQUEST_MAX_BYTES = 20_971_520

#: The longest text one `host.speak()` may carry, in characters (Unicode scalar
#: values, about twenty seconds spoken). A longer text is REFUSED with
#: `BAD_ARGUMENTS`, never cut short (`plugins::speech::SPEAK_TEXT_MAX_CHARS`).
#: A plugin's speaking time is budgeted in characters on top of this, so a
#: backlog never holds the person's own reply past the speech queue's wait limit.
SPEAK_TEXT_MAX_CHARS = 300

#: The most pictures one tool call is handed: `generate_image` editing what the
#: person attached, and a plugin tool that declared `wants_attachments`
#: (`PluginCallToolRequest.attachments`). The newest are kept, within
#: `plugin_image_request_max_bytes`, and a picture left out is counted, never
#: dropped in silence (`ai::turn_attachments::MAX_IMAGES`).
IMAGE_INPUT_MAX_IMAGES = 4

#: The most settings one `host.requestSettingsChange()` may ask for, each path
#: once. All of them change or none (`ai::tools::settings_tools::MAX_CHANGES`,
#: the assistant's own bound).
SETTINGS_CHANGE_MAX_CHANGES = 8

#: The longest reason one `host.requestSettingsChange()` may give the person, in
#: characters: it is shown on the card whole, so a longer one is REFUSED, never
#: cut (`plugins::settings_request::REASON_MAX_CHARS`).
SETTINGS_CHANGE_REASON_MAX_CHARS = 140

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
    "MUSIC_SNAPSHOT_HEARTBEAT_SECS",
    "MUSIC_SESSION_STALE_SECS",
    "MUSIC_SNAPSHOT_MAX_SESSIONS",
    "MUSIC_SEARCH_MAX_ITEMS",
    "PLUGIN_MAX_MESSAGE_BYTES",
    "PLUGIN_IMAGE_REQUEST_MAX_BYTES",
    "SPEAK_TEXT_MAX_CHARS",
    "IMAGE_INPUT_MAX_IMAGES",
    "SETTINGS_CHANGE_MAX_CHANGES",
    "SETTINGS_CHANGE_REASON_MAX_CHARS",
]

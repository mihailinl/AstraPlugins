// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * AUTO-GENERATED — DO NOT EDIT.
 *
 * Produced by `tools/gen-limits.mjs` from `spec/limits.yaml`.
 * Regenerate with `node tools/gen-limits.mjs` at the repo root.
 * These numbers are shared with the Astra daemon; changing one here without
 * changing the spec is a silent protocol break, which is why this file is
 * generated and CI re-runs the generator with `--check`.
 */

/** SHA-256 of the `spec/limits.yaml` these constants were generated from. */
export const SPEC_SHA256 = "aac2be63b966117068edd56a5faaeb342aa60fccb20b75509366024ba2d3939e";

/**
 * Capacity of the audio channel that carries streaming-STT chunks from the
 * daemon's voice pipeline into the plugin process, in chunks.
 *
 * It bounds TWO channels in series and both must be this value: the daemon's
 * (`SttSession` -> `SttProcess` bridge) and the SDK's (inbound gRPC stream ->
 * the plugin's `stt_transcribe_stream` hook). The smaller of the two is the
 * real capacity, which is how a 32-slot SDK channel silently capped a 500-slot
 * daemon one. 500 is ~10 s of audio: the worst-case wake-word seed dump (~8 s
 * in 100 ms batches) plus live audio arriving while a slow provider is still
 * inferring, with headroom, so a busy provider back-pressures instead of the
 * audio loop dropping chunks.
 */
export const STT_AUDIO_CHANNEL_CAPACITY = 500;

/**
 * How long the daemon waits for a freshly spawned plugin process to produce its
 * first line of output before declaring the start a failure, in seconds.
 * An SDK must reach "ready" — bind its port, print its line — inside this.
 */
export const PLUGIN_START_TIMEOUT_SECS = 20;

/**
 * Grace the daemon gives a plugin's `Shutdown` RPC on a normal stop (user stop
 * / disable / uninstall) before it kills the process group, in seconds.
 * An SDK's own drain budget must not exceed this, or the SDK's tidy path never
 * gets to run: the daemon kills it first. (Daemon shutdown passes a much
 * shorter grace, bounded by the whole-teardown deadline — that path is
 * deliberately not this number.)
 */
export const PLUGIN_STOP_GRACE_SECS = 5;

/**
 * Maximum combined uncompressed size the daemon will extract from one
 * `.astraplugin` archive, in bytes (500 MiB). Zip-bomb mitigation.
 * A packaging tool that produces a bundle over this makes an uninstallable
 * plugin, so the CLI is expected to refuse at build time.
 */
export const MAX_EXTRACT_BYTES = 524288000;

/**
 * Maximum number of entries in one `.astraplugin` archive. Zip-bomb
 * mitigation, same contract as `max_extract_bytes`.
 */
export const MAX_ARCHIVE_ENTRIES = 10000;

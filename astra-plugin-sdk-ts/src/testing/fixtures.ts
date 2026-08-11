/**
 * Deterministic fixtures for plugin tests.
 *
 * Everything here is generated from a seed, not read from disk: a committed WAV
 * is a binary blob nobody diffs, and the properties these fixtures exist to
 * exercise (how many chunks, at what rate, in what order) are exactly the ones a
 * blob hides. Two runs produce identical bytes, so a test may assert on a
 * checksum.
 */

import { STT_AUDIO_CHANNEL_CAPACITY } from "../generated/limits.js";
import type { AudioChunk } from "../types.js";

/** The rate Astra's voice pipeline speaks. Nothing here is resampled. */
export const SAMPLE_RATE = 16000;

/**
 * `ms` of 16-bit little-endian mono PCM at {@link SAMPLE_RATE}.
 *
 * A sine, not noise and not silence: silence is indistinguishable from a
 * dropped chunk, and noise cannot be checked by eye when a test fails.
 */
export function pcm16(ms: number, opts: { freq?: number; amplitude?: number; phase?: number } = {}): Buffer {
  const freq = opts.freq ?? 440;
  const amplitude = opts.amplitude ?? 0.25;
  const samples = Math.round((SAMPLE_RATE * ms) / 1000);
  const buf = Buffer.alloc(samples * 2);
  for (let i = 0; i < samples; i++) {
    const t = (i + (opts.phase ?? 0)) / SAMPLE_RATE;
    const value = Math.round(Math.sin(2 * Math.PI * freq * t) * amplitude * 32767);
    buf.writeInt16LE(value, i * 2);
  }
  return buf;
}

/** How a golden utterance is shaped. Defaults reproduce the 500-slot condition. */
export interface UtteranceOptions {
  /**
   * Milliseconds of wake-word seed audio the daemon dumps in one burst at the
   * start of an utterance. ~8 s is the worst case `spec/limits.yaml` sizes the
   * channel for.
   */
  seedMs?: number;
  /** Batch size of the seed dump. The daemon sends it in 100 ms batches. */
  seedChunkMs?: number;
  /** Milliseconds of live audio after the seed. */
  liveMs?: number;
  /** Frame size of the live audio. */
  liveChunkMs?: number;
  /** Set `isLast` on the final chunk. */
  markLast?: boolean;
  /** Per-utterance decoding options, carried on the first chunk only. */
  options?: AudioChunk["options"];
}

/**
 * A golden utterance as the daemon streams it: a wake-seed burst, then live
 * frames.
 *
 * The defaults deliberately produce **more chunks than
 * `STT_AUDIO_CHANNEL_CAPACITY`**, because that is the condition under test. The
 * SDK once buffered 32 chunks against a daemon channel of 500, and everything
 * past the first fraction of a second of every utterance was silently dropped —
 * a bug no fixture with a two-second sample can reach.
 */
export function utteranceChunks(opts: UtteranceOptions = {}): AudioChunk[] {
  const seedMs = opts.seedMs ?? 8000;
  const seedChunkMs = opts.seedChunkMs ?? 100;
  const liveChunkMs = opts.liveChunkMs ?? 20;
  // Enough live frames that seed + live is comfortably past the bound.
  const liveMs = opts.liveMs ?? (STT_AUDIO_CHANNEL_CAPACITY + 40 - seedMs / seedChunkMs) * liveChunkMs;

  const chunks: AudioChunk[] = [];
  let phase = 0;
  const push = (ms: number, freq: number) => {
    const data = pcm16(ms, { freq, phase });
    phase += (SAMPLE_RATE * ms) / 1000;
    chunks.push({ data, sampleRate: chunks.length === 0 ? SAMPLE_RATE : 0 });
  };

  for (let t = 0; t < seedMs; t += seedChunkMs) push(seedChunkMs, 220);
  for (let t = 0; t < liveMs; t += liveChunkMs) push(liveChunkMs, 440);

  if (chunks.length === 0) chunks.push({ data: Buffer.alloc(0), sampleRate: SAMPLE_RATE });
  if (opts.options) chunks[0].options = opts.options;
  if (opts.markLast ?? true) chunks[chunks.length - 1].isLast = true;
  return chunks;
}

/** Total PCM bytes across chunks — the number a truncating bridge gets wrong. */
export function totalBytes(chunks: readonly AudioChunk[]): number {
  return chunks.reduce((n, c) => n + c.data.length, 0);
}

/**
 * A cheap order-sensitive checksum (FNV-1a, 32-bit).
 *
 * Order-sensitive on purpose: a bridge that delivers every chunk but reorders
 * two of them produces the same byte count and a different checksum.
 */
export function checksum(data: Buffer | readonly AudioChunk[]): number {
  const bufs = Buffer.isBuffer(data) ? [data] : data.map((c) => c.data);
  let hash = 0x811c9dc5;
  for (const buf of bufs) {
    for (const byte of buf) {
      hash ^= byte;
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
  }
  return hash >>> 0;
}

/**
 * A `FirehoseEventMsg` stream: one whole assistant turn across two
 * conversations, in the shape `onConversationEvent` receives.
 */
export function firehoseEvents(): { conversationId: string; event: Record<string, unknown> }[] {
  const conv = "conv-1";
  return [
    { conversationId: conv, event: { userMessage: { messageId: "m1", text: "what time is it?" } } },
    { conversationId: conv, event: { assistantStarted: { messageId: "m2" } } },
    { conversationId: conv, event: { textDelta: { messageId: "m2", text: "Let me " } } },
    { conversationId: conv, event: { textDelta: { messageId: "m2", text: "check." } } },
    {
      conversationId: conv,
      event: { toolCall: { messageId: "m2", id: "t1", name: "get_time", argumentsJson: "{}" } },
    },
    { conversationId: conv, event: { toolResult: { id: "t1", resultJson: '{"time":"12:00"}' } } },
    { conversationId: conv, event: { textDelta: { messageId: "m2", text: " It is noon." } } },
    { conversationId: conv, event: { assistantFinished: { messageId: "m2" } } },
    { conversationId: "conv-2", event: { userMessage: { messageId: "m3", text: "thanks" } } },
    { conversationId: "conv-2", event: { error: { message: "provider unavailable" } } },
  ];
}

/**
 * Configs a plugin's `onConfigChanged` must survive.
 *
 * Not hypothetical: config arrives as a JSON string the daemon assembled from
 * user input and from an older version of this plugin's own schema. Every entry
 * here has a name saying which real shape it is.
 */
export function configFuzz(): { name: string; config: Record<string, unknown> }[] {
  return [
    { name: "empty", config: {} },
    { name: "null values", config: { indent: null, name: null } },
    { name: "wrong types", config: { indent: "two", enabled: "yes", retries: [] } },
    { name: "numbers as strings", config: { indent: "2", retries: "3" } },
    { name: "unknown keys from a newer version", config: { future_flag: true, nested: { a: 1 } } },
    { name: "missing every key", config: { unrelated: 1 } },
    { name: "deeply nested", config: { a: { b: { c: { d: { e: [1, 2, { f: "g" }] } } } } } },
    { name: "unicode and bidi", config: { name: "‮gnp.txt‬ ключ 名前 🎧" } },
    { name: "very long string", config: { note: "x".repeat(64 * 1024) } },
    { name: "numeric edges", config: { indent: -1, ratio: 1e308, tiny: 5e-324, zero: -0 } },
    { name: "prototype-ish keys", config: { __proto__: { polluted: true }, constructor: "x" } },
  ];
}

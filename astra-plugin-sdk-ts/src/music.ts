// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

/**
 * The `music_provider` capability: report what music services play, drive them.
 *
 * A plugin declaring `[capabilities] music_provider = true` is a source of media
 * sessions for Astra's media hub — the music widget, the Dynamic Island and the
 * assistant's media tools then reach the services it talks to.
 *
 * - **Reporting is push.** Call `this.music.publish(services, sessions)` whenever
 *   what you report changes. The SDK serves the daemon's `MusicSubscribe` stream
 *   from it: the latest snapshot at once, on every publish, and every
 *   `MUSIC_SNAPSHOT_HEARTBEAT_SECS`. Every publish is the WHOLE set: a session
 *   left out has ended.
 * - **Answering** is four hooks — `musicControl` (required), `musicGetQueue`,
 *   `musicSearch`, `musicPlay`. A refusal you mean is
 *   `throw new MusicRefusal("no_active_device", "…")`: an ANSWER the daemon shows
 *   to the person. Any other throw reports the plugin as failing.
 */

import {
  MUSIC_SEARCH_MAX_ITEMS,
  MUSIC_SNAPSHOT_HEARTBEAT_SECS,
  MUSIC_SNAPSHOT_MAX_SESSIONS,
} from "./generated/limits.js";

export type MusicErrorCode =
  | "not_supported"
  | "not_found"
  | "no_active_device"
  | "auth"
  | "premium_required"
  | "rate_limited"
  | "unavailable"
  | "not_configured";

const MUSIC_ERROR_CODES: readonly MusicErrorCode[] = [
  "not_supported", "not_found", "no_active_device", "auth", "premium_required",
  "rate_limited", "unavailable", "not_configured",
];

/** The verbs a session may list in `controls`. The daemon drops anything else. */
export const MUSIC_CONTROLS = [
  "play", "pause", "next", "previous", "seek", "like", "unlike", "shuffle", "repeat", "volume",
  "queue", "play_into",
] as const;

/** Throw from a music hook to ANSWER with a refusal rather than fail. */
export class MusicRefusal extends Error {
  readonly code: MusicErrorCode;
  readonly retryAfterSecs: number;

  constructor(code: MusicErrorCode, message: string, retryAfterSecs = 0) {
    super(message);
    if (!MUSIC_ERROR_CODES.includes(code)) {
      // Checked here, so a typo fails in the plugin's own test rather than
      // reaching the daemon as an unknown code it reads as "unavailable".
      throw new TypeError(`unknown music refusal code: ${code}`);
    }
    this.name = "MusicRefusal";
    this.code = code;
    this.retryAfterSecs = Math.max(0, Math.trunc(retryAfterSecs));
  }
}

/** A service the plugin reaches, signed in or not. */
export interface MusicService {
  serviceId: string;
  /** For the user; a `$key` resolves through the plugin's locales. */
  name: string;
  /** "ready" | "signed_out" | "error" | "disabled" — default "ready". */
  status?: string;
  statusMessage?: string;
  canSearch?: boolean;
  canPlay?: boolean;
}

/** One playback a service reports. */
export interface MusicSession {
  /** `[A-Za-z0-9._-]{1,64}`, stable while the plugin runs. */
  sessionKey: string;
  serviceId: string;
  /** The audio may be coming out of THIS computer. */
  thisDevice?: boolean;
  deviceName?: string;
  /** OS session ids of an app that plays nothing but this service. */
  exclusiveAppHints?: string[];
  /** Hosts of many things (browsers): the song must agree too. */
  sharedAppHints?: string[];
  /** "playing" | "paused" | "stopped" | "buffering". */
  status?: string;
  title?: string;
  artist?: string;
  album?: string;
  /** https only. */
  artworkUrl?: string;
  positionSeconds?: number;
  durationSeconds?: number;
  trackRef?: string;
  trackUrl?: string;
  liked?: boolean;
  shuffle?: boolean;
  /** "off" | "track" | "context". */
  repeat?: string;
  /** -1 when unknown. */
  volumePercent?: number;
  controls?: string[];
}

/** Something in a catalogue or a queue. */
export interface MusicItem {
  /** Your own reference; it comes back in `musicPlay`. */
  itemRef: string;
  /** "track" | "album" | "artist" | "playlist" | "wave". */
  kind: string;
  title: string;
  subtitle?: string;
  album?: string;
  artworkUrl?: string;
  durationSeconds?: number;
  liked?: boolean;
  serviceId?: string;
}

export interface MusicQueue {
  items: MusicItem[];
  /** The playing item's index in `items`, -1 if none. */
  currentIndex: number;
}

export interface MusicPlayed {
  item?: MusicItem | null;
  sessionKey?: string;
}

export interface MusicControlRequest {
  sessionKey: string;
  action: string;
  /** "seek": seconds; "volume": "0".."100"; "shuffle": "on" | "off"; "repeat": "off" | "track" | "context". */
  value: string;
}

export interface MusicQueueRequest {
  sessionKey: string;
  limit: number;
}

export interface MusicSearchRequest {
  query: string;
  kind: string;
  limit: number;
  serviceId: string;
  language: string;
}

export interface MusicPlayRequest {
  itemRef: string;
  query: string;
  kind: string;
  /** "now" | "next" | "end". */
  mode: string;
  sessionKey: string;
  serviceId: string;
}

const str = (v: unknown): string => (typeof v === "string" ? v : "");
const num = (v: unknown, fallback: number): number => {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? Math.trunc(n) : fallback;
};

export function musicControlFromWire(w: Record<string, unknown>): MusicControlRequest {
  return { sessionKey: str(w.sessionKey), action: str(w.action), value: str(w.value) };
}

export function musicQueueFromWire(w: Record<string, unknown>): MusicQueueRequest {
  return { sessionKey: str(w.sessionKey), limit: Math.min(num(w.limit, 20), 50) };
}

export function musicSearchFromWire(w: Record<string, unknown>): MusicSearchRequest {
  return {
    query: str(w.query),
    kind: str(w.kind),
    limit: Math.min(num(w.limit, 10), MUSIC_SEARCH_MAX_ITEMS),
    serviceId: str(w.serviceId),
    language: str(w.language),
  };
}

export function musicPlayFromWire(w: Record<string, unknown>): MusicPlayRequest {
  return {
    itemRef: str(w.itemRef),
    query: str(w.query),
    kind: str(w.kind),
    mode: str(w.mode) || "now",
    sessionKey: str(w.sessionKey),
    serviceId: str(w.serviceId),
  };
}

export function musicItemWire(i: MusicItem): Record<string, unknown> {
  return {
    itemRef: i.itemRef,
    kind: i.kind,
    title: i.title,
    subtitle: i.subtitle ?? "",
    album: i.album ?? "",
    artworkUrl: i.artworkUrl ?? "",
    durationSeconds: i.durationSeconds ?? 0,
    liked: i.liked ?? false,
    serviceId: i.serviceId ?? "",
  };
}

function serviceWire(s: MusicService): Record<string, unknown> {
  return {
    serviceId: s.serviceId,
    name: s.name,
    status: s.status || "ready",
    statusMessage: s.statusMessage ?? "",
    canSearch: s.canSearch ?? false,
    canPlay: s.canPlay ?? false,
  };
}

function sessionWire(s: MusicSession): Record<string, unknown> {
  return {
    sessionKey: s.sessionKey,
    serviceId: s.serviceId,
    thisDevice: s.thisDevice ?? false,
    deviceName: s.deviceName ?? "",
    exclusiveAppHints: s.exclusiveAppHints ?? [],
    sharedAppHints: s.sharedAppHints ?? [],
    status: s.status || "stopped",
    title: s.title ?? "",
    artist: s.artist ?? "",
    album: s.album ?? "",
    artworkUrl: s.artworkUrl ?? "",
    positionSeconds: s.positionSeconds ?? 0,
    durationSeconds: s.durationSeconds ?? 0,
    trackRef: s.trackRef ?? "",
    trackUrl: s.trackUrl ?? "",
    liked: s.liked ?? false,
    shuffle: s.shuffle ?? false,
    repeat: s.repeat || "off",
    volumePercent: s.volumePercent ?? -1,
    controls: s.controls ?? [],
  };
}

/** A refusal as the three in-band fields, or `null` for any other throw. */
export function musicRefusalWire(e: unknown): Record<string, unknown> | null {
  if (!(e instanceof MusicRefusal)) return null;
  return { errorCode: e.code, errorMessage: e.message, retryAfterSecs: e.retryAfterSecs };
}

export type MusicSnapshotWire = { services: Record<string, unknown>[]; sessions: Record<string, unknown>[] };

/** What the plugin last reported, served as the `MusicSubscribe` stream. */
export class MusicPublisher {
  private current: MusicSnapshotWire = { services: [], sessions: [] };
  private version = 0;
  private waiters = new Set<() => void>();

  /** Replace everything reported. A session left out has ended. */
  publish(services: Iterable<MusicService> = [], sessions: Iterable<MusicSession> = []): void {
    this.current = {
      services: [...services].map(serviceWire),
      sessions: [...sessions].slice(0, MUSIC_SNAPSHOT_MAX_SESSIONS).map(sessionWire),
    };
    this.version += 1;
    const waiters = [...this.waiters];
    this.waiters.clear();
    for (const wake of waiters) wake();
  }

  /** The latest snapshot, as the daemon will receive it. */
  get snapshot(): MusicSnapshotWire {
    return this.current;
  }

  /** Whether the latest snapshot reports a session with this key. */
  knowsSession(sessionKey: string): boolean {
    return this.current.sessions.some((s) => s.sessionKey === sessionKey);
  }

  /** The latest snapshot now, then on every publish and every heartbeat. */
  async *stream(
    heartbeatMs = MUSIC_SNAPSHOT_HEARTBEAT_SECS * 1000,
    signal?: { cancelled: boolean },
  ): AsyncGenerator<MusicSnapshotWire> {
    let seen = this.version;
    yield this.current;
    while (!signal?.cancelled) {
      if (this.version === seen) {
        await new Promise<void>((resolve) => {
          // A heartbeat that fires first takes its waiter back out, or a quiet
          // provider would collect one per beat until the next publish.
          const wake = () => {
            clearTimeout(timer);
            this.waiters.delete(wake);
            resolve();
          };
          const timer = setTimeout(wake, heartbeatMs);
          this.waiters.add(wake);
        });
      }
      if (signal?.cancelled) return;
      seen = this.version;
      yield this.current;
    }
  }
}

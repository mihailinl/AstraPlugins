// A deterministic ZIP writer that can also write *malformed* archives.
//
// Every other ZIP writer in this project refuses to emit a bundle that breaks
// the format. This one has to: half the vectors in this directory exist to be
// refused, and a duplicate entry name, a symlink mode, a compressed
// `MANIFEST.json` and a central directory that points somewhere other than the
// local header at offset 0 are all things no honest packer will produce for us.
//
// Determinism is the other requirement, and it is not decoration: the goldens
// are committed with their digests, so regenerating them on another machine
// must reproduce the same bytes or `SHA256SUMS` goes red for a reason that has
// nothing to do with the format. Fixed 1980-01-01 timestamps, no extra fields,
// no comments, caller-controlled order, stored or deflate at a pinned level.

import zlib from "node:zlib";

const SIG_LOCAL = 0x04034b50;
const SIG_CENTRAL = 0x02014b50;
const SIG_EOCD = 0x06054b50;

// 1980-01-01 00:00:00, the earliest a DOS timestamp can express — the same
// value the CLI's `fixed_mtime()` pins.
const DOS_TIME = 0;
const DOS_DATE = 0x0021;

export const S_IFMT = 0o170000;
export const S_IFLNK = 0o120000;
export const S_IFDIR = 0o040000;

export const STORED = 0;
export const DEFLATE = 8;

/**
 * @typedef {object} ZipEntry
 * @property {string} name archive path, written verbatim (traversal included)
 * @property {Buffer|string} data uncompressed content
 * @property {number} [mode] full st_mode; 0o100644 if absent. Pass
 *   `S_IFLNK | 0o777` to write a symlink entry.
 * @property {number} [method] STORED (default) or DEFLATE
 * @property {boolean} [hidden] write the local record but omit it from the
 *   central directory — the raw material for a central/local disagreement
 */

/**
 * Write an archive.
 *
 * `centralOverrides` is keyed by central-directory index and can rewrite any
 * field of an entry's central record, including `offset`. That is how the
 * `header-disagree` vector is built: the central directory names
 * `MANIFEST.json` and points at a local record that is not the one at byte
 * zero, which is the exact split between "what the registry hashed" and "what
 * the daemon enforces".
 *
 * @param {ZipEntry[]} entries
 * @param {Record<number, Partial<{name: string, offset: number}>>} [centralOverrides]
 * @returns {Buffer}
 */
export function writeZip(entries, centralOverrides = {}) {
  const locals = [];
  const records = [];
  let offset = 0;

  for (const e of entries) {
    const name = Buffer.from(e.name, "utf8");
    const raw = Buffer.isBuffer(e.data) ? e.data : Buffer.from(e.data, "utf8");
    const method = e.method ?? STORED;
    // Level 6 — the CLI's REPRODUCIBLE_COMPRESSION_LEVEL. An encoder default is
    // a property of whichever flate backend is linked, not of this format.
    const stored = method === DEFLATE ? zlib.deflateRawSync(raw, { level: 6 }) : raw;
    const crc = zlib.crc32(raw) >>> 0;
    const mode = e.mode ?? 0o100644;

    const local = Buffer.alloc(30 + name.length);
    local.writeUInt32LE(SIG_LOCAL, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0, 6);
    local.writeUInt16LE(method, 8);
    local.writeUInt16LE(DOS_TIME, 10);
    local.writeUInt16LE(DOS_DATE, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(stored.length, 18);
    local.writeUInt32LE(raw.length, 22);
    local.writeUInt16LE(name.length, 26);
    local.writeUInt16LE(0, 28);
    name.copy(local, 30);
    locals.push(local, stored);

    records.push({
      name,
      method,
      crc,
      compressedSize: stored.length,
      size: raw.length,
      mode,
      offset,
      hidden: e.hidden === true,
    });
    offset += local.length + stored.length;
  }

  const centrals = [];
  let index = 0;
  for (const r of records) {
    if (r.hidden) continue;
    const o = centralOverrides[index] ?? {};
    index++;
    const name = o.name !== undefined ? Buffer.from(o.name, "utf8") : r.name;
    const at = o.offset !== undefined ? o.offset : r.offset;

    const central = Buffer.alloc(46 + name.length);
    central.writeUInt32LE(SIG_CENTRAL, 0);
    central.writeUInt16LE(0x031e, 4); // made by: unix, zip 3.0
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0, 8);
    central.writeUInt16LE(r.method, 10);
    central.writeUInt16LE(DOS_TIME, 12);
    central.writeUInt16LE(DOS_DATE, 14);
    central.writeUInt32LE(r.crc, 16);
    central.writeUInt32LE(r.compressedSize, 20);
    central.writeUInt32LE(r.size, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt16LE(0, 30);
    central.writeUInt16LE(0, 32);
    central.writeUInt16LE(0, 34);
    central.writeUInt16LE(0, 36);
    central.writeUInt32LE(((r.mode & 0xffff) << 16) >>> 0, 38);
    central.writeUInt32LE(at, 42);
    name.copy(central, 46);
    centrals.push(central);
  }

  const cd = Buffer.concat(centrals);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(SIG_EOCD, 0);
  eocd.writeUInt16LE(0, 4);
  eocd.writeUInt16LE(0, 6);
  eocd.writeUInt16LE(centrals.length, 8);
  eocd.writeUInt16LE(centrals.length, 10);
  eocd.writeUInt32LE(cd.length, 12);
  eocd.writeUInt32LE(offset, 16);
  eocd.writeUInt16LE(0, 20);

  return Buffer.concat([...locals, cd, eocd]);
}

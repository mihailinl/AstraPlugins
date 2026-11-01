# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
# Generator of stored-dd.zip (astra-ce's review round 2, 2026-11-01). See README.md.
import struct, zlib
T, D = 0x0000, 0x5021  # 2020-01-01
def lfh(name, method, flags, crc, csz, usz, extra=b''):
    return struct.pack('<IHHHHHIIIHH', 0x04034b50, 20, flags, method, T, D, crc, csz, usz, len(name), len(extra)) + name + extra
def cdh(name, method, flags, crc, csz, usz, off, extra=b''):
    return struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, 20, 20, flags, method, T, D, crc, csz, usz, len(name), len(extra), 0, 0, 0, 0, off) + name + extra
def eocd(n, cdsz, cdoff):
    return struct.pack('<IHHHHIIH', 0x06054b50, 0, 0, n, n, cdsz, cdoff, 0)
def deflate(b):
    c = zlib.compressobj(9, zlib.DEFLATED, -15); return c.compress(b) + c.flush()
DOC = b'word/document.xml'
# ---- 1. split EOCD: zip 9 reads CD-A (benign), zip 4 falls back to CD-B (bomb)
benign = b'<w:document/>'; bomb = b'\0' * (64 << 20); dbomb = deflate(bomb)
e1 = lfh(DOC, 0, 0, zlib.crc32(benign), len(benign), len(benign)) + benign
o2 = len(e1); e2 = lfh(DOC, 8, 0, zlib.crc32(bomb), len(dbomb), 1000) + dbomb
o3 = o2 + len(e2); junk = b'x'; e3 = lfh(b'junk.txt', 0, 0, zlib.crc32(junk), 1, 1) + junk
body = e1 + e2 + e3
cdB = cdh(DOC, 8, 0, zlib.crc32(bomb), len(dbomb), 1000, o2)
eB = eocd(1, len(cdB), len(body))
badup = b'\x01' + struct.pack('<I', 0xDEADBEEF) + b'other.txt'
cdA = cdh(DOC, 0, 0, zlib.crc32(benign), len(benign), len(benign), 0) + cdh(b'junk.txt', 0, 0, zlib.crc32(junk), 1, 1, o3, struct.pack('<HH', 0x7075, len(badup)) + badup)
offA = len(body) + len(cdB) + len(eB)
open('split.docx', 'wb').write(body + cdB + eB + cdA + eocd(2, len(cdA), offA))
# ---- 2. stored bit-3 entry, no descriptor at its recorded end; a CRC-matching descriptor after B instead
A = b'harmless notes\n'
a_l = lfh(b'notes.txt', 0, 0x08, 0, 0, 0)
evil = b'#!/bin/sh\necho pwned\n'
b_off = len(a_l) + len(A)
b_l = lfh(b'launch.sh', 0, 0, zlib.crc32(evil), len(evil), len(evil))
swallowed = A + b_l + evil
dd = struct.pack('<IIII', 0x08074b50, zlib.crc32(swallowed), len(swallowed), len(swallowed))
arch = a_l + A + b_l + evil + dd
cd = cdh(b'notes.txt', 0, 0x08, zlib.crc32(A), len(A), len(A), 0) + cdh(b'launch.sh', 0, 0, zlib.crc32(evil), len(evil), len(evil), b_off)
open('stored-dd.zip', 'wb').write(arch + cd + eocd(2, len(cd), len(arch)))

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Minice — https://minice.ai
# Generator of the two ZIP cloaking vectors in this directory (astra-ce's review, 2026-11-01). See README.md.
import struct, zlib
def lfh(name, method, flags, crc, csz, usz, extra=b''):
    return struct.pack('<IHHHHHIIIHH', 0x04034b50, 20, flags, method, 0, 0x21, crc, csz, usz, len(name), len(extra)) + name + extra
def cdh(name, method, flags, crc, csz, usz, off, extra=b''):
    return struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, 20, 20, flags, method, 0, 0x21, crc, csz, usz, len(name), len(extra), 0, 0, 0, 0, off) + name + extra
def eocd(n, cdsz, cdoff):
    return struct.pack('<IHHHHIIH', 0x06054b50, 0, 0, n, n, cdsz, cdoff, 0)
def upath(target, raw):
    body = b'\x01' + struct.pack('<I', zlib.crc32(raw)) + target
    return struct.pack('<HH', 0x7075, len(body)) + body
# Case 1: Unicode Path field. Both headers agree; raw name notes.txt, upath launch.sh
raw=b'notes.txt'; data=b'payload'; c=zlib.crc32(data); ex=upath(b'launch.sh', raw)
l=lfh(raw,0,0,c,len(data),len(data),ex)+data
cd=cdh(raw,0,0,c,len(data),len(data),0,ex)
open('upath.zip','wb').write(l+cd+eocd(1,len(cd),len(l)))
# Case 2: deflate slack + data descriptor; a streaming reader sees a.txt + readme.txt, CD sees a.txt + launch.sh
X=b'hello world\n'; co=zlib.compressobj(9, zlib.DEFLATED, -15); dX=co.compress(X)+co.flush()
cX=zlib.crc32(X)
A_l=lfh(b'a.txt',8,0x08,0,0,0)
fakeDD=struct.pack('<IIII',0x08074b50,cX,len(dX),len(X))
evil=b'#!/bin/sh\necho pwned\n'; ce=zlib.crc32(evil)
B_l=lfh(b'launch.sh',0,0,ce,len(evil),len(evil))
H_name=b'readme.txt'; H_hdr_len=30+len(H_name)
# H data = B_l + evil exactly (H header sits right before B's header)
H_data=B_l+evil
H_l=lfh(H_name,0,0,zlib.crc32(H_data),len(H_data),len(H_data))
body=A_l+dX+fakeDD+H_l     # A's claimed compressed range ends here
N=len(dX)+len(fakeDD)+len(H_l)
hB=len(body)
arch=body+B_l+evil
cd=cdh(b'a.txt',8,0x08,cX,N,len(X),0)+cdh(b'launch.sh',0,0,ce,len(evil),len(evil),hB)
open('slack.zip','wb').write(arch+cd+eocd(2,len(cd),len(arch)))

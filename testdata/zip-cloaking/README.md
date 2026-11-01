# `testdata/zip-cloaking`

Raw ZIP-cloaking attack vectors used by `astra-plugin-cli`'s
`commands::verify::cloaking` tests. These are **not** `.astraplugin` bundles —
no `MANIFEST.json`, no manifest digest — they exercise `Bundle::open`'s
lower-level ZIP structural hardening (`validate_header_consistency`, the bit-3
refusal, the Unicode Path refusal, `verify_no_deflate_slack`) directly,
independent of the bundle format itself. That is also why this lives beside
`testdata/bundles` rather than inside it: the bundle vectors are vendored
cross-repo (Astra, astra-registry) because all three implementations read the
*format*; these are CLI-only, about the ZIP container underneath it.

| file | sha256 | what it demonstrates |
|---|---|---|
| `stored-dd.zip` | `3841c473f7ade57d1efca72aa33847d9508773df2147797a8bdb873828f691fb` | A **Stored** entry (`notes.txt`) with general-purpose bit 3 set. Its real trailing data descriptor sits *after* the next entry (`launch.sh`), with a CRC32 computed over all three (`notes.txt`'s content + `launch.sh`'s entire local header + content) — so a streaming reader with no central directory, watching for a CRC match to find where `notes.txt` ends, absorbs `launch.sh` into it entirely and never sees a second entry at all. The central directory sees two ordinary, non-overlapping entries. `Bundle::open` refuses this archive outright because of the bit-3 flag alone, before any of that ambiguity matters. |

Received from astra-ce's second review round (2026-10-31) with this sha256
already quoted; this file is kept byte-for-byte as received rather than
rebuilt, since reproducing a streaming-reader-vs-central-directory CRC
collision by hand is exactly the kind of fixture worth keeping literally
rather than re-deriving.

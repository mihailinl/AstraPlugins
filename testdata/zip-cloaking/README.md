<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 Minice — https://minice.ai
-->

# ZIP cloaking vectors

Two archives that a validator and an extractor read differently, and that `zip` 9's
`ZipArchive::validate_header_consistency` does NOT refuse on its own. Every reader of an archive that
Astra later installs must refuse both: the AstraPlugins CLI (`astra-plugin verify`), the registry
bot's bundle reader, the games catalogue's ingest, minice's content upload ingest, and the Astra daemon.
Each consumer pins these bytes by the sha256 in `SHA256SUMS`, so all of them test the same archives.

| file | shape | expected |
|---|---|---|
| `slack.zip` | a Deflated entry with a data descriptor (general-purpose bit 3) whose central-directory `compressed_size` runs past the real end of the deflate stream; the slack hides a local header that swallows the next entry, so a streaming reader and a central-directory reader see different payloads | **reject: E_ZIP_HEADERS_INCONSISTENT** — inflate each entry raw and require the stream to end exactly at `compressed_size`, matching the declared size and CRC |
| `upath.zip` | an entry carrying the `0x7075` Unicode Path extra field, which renames it for readers that honour the field | **reject: E_ZIP_HEADERS_INCONSISTENT** — refuse any entry carrying `0x7075` |
| `stored-dd.zip` | a STORED entry with a data descriptor (bit 3) whose real descriptor sits after the NEXT entry, so a scanning reader (e.g. Windows `tar.exe` on a pipe) and a central-directory reader see different payloads | **reject: E_ZIP_HEADERS_INCONSISTENT** — refuse bit 3 where the producer never writes it; otherwise require a descriptor EXACTLY at the entry's recorded end (signature optional) whose CRC and sizes equal the central record |

`gen.py` regenerates `slack.zip` and `upath.zip`, and `gen_stored_dd.py` regenerates `stored-dd.zip`, deterministically.

**Two rules every checker must also keep (review round 2):** drain the inflater after input EOF before judging "the stream ends exactly at compressed_size", or legitimate near-zero files just over k×64 KiB are falsely refused; and run the deflate-end check on EVERY Deflated entry, including those with ZIP64 sentinels. Found by astra-ce's review on 2026-11-01;
committed here as the shared golden at minice-01's and astra-ce's request.

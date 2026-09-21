#!/usr/bin/env bash
# Re-derive every digest in `digest-vectors.json` with coreutils, by hand.
#
#     bash testdata/locales/digest-handcheck.sh
#
# ── why this exists and not just the two test suites ───────────────────────
#
# `digest-vectors.json` is the only thing that has ever compared the two
# implementations of the lock digest: `digest` in
# `astra-plugin-cli/src/commands/locale.rs`, which WRITES the values in a
# bundle's `locales.lock.json`, and `englishDigest` in
# `astra-registry/bot/lib/locales.mjs`, which READS them. Each of the two is
# held to this table by its own suite, in its own repository, on its own CI.
#
# That only means something if the table itself was not written by either of
# them. Every number in it is what `sha256sum` returns for the vector's exact
# UTF-8 bytes, and this script is how anybody re-derives that without running
# Rust or Node. `testdata/bundles/handcheck.sh` makes the same argument about
# the bundle digests in the same words: two programs that share a mistake can
# agree with each other, they cannot agree with coreutils.
#
# Python appears here ONLY to decode a JSON string into bytes and write them to
# a pipe. It does not hash anything — `hashlib` and Node's `crypto` are both
# OpenSSL and would not be a second opinion. `sha256sum` is.
#
# ── what it checks ─────────────────────────────────────────────────────────
#
#   1. a FLOOR on how many vectors were read, before it compares any of them,
#      so a file that stopped parsing fails as a file that stopped parsing;
#   2. every `digest` against `sha256sum`;
#   3. every `digest` is exactly 12 lower-case hex — a width change on either
#      side is this gap's named failure and must not be absorbed here;
#   4. the five pairs that must NOT collide. A table whose halves are equal
#      proves nothing about a normalisation added to one side, and a collision
#      is the one defect a per-vector comparison cannot see.

set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
file="$here/digest-vectors.json"

# The floor. A number rather than a range, written above the reader: an empty
# or unparseable table must fail as itself and not pass as a clean run.
MIN_VECTORS=20

if [ ! -f "$file" ]; then
  echo "FAIL  $file is missing. It is the only thing that compares the two implementations of the lock digest." >&2
  exit 1
fi

count=$(python3 -c '
import json,sys
print(len(json.load(open(sys.argv[1]))["vectors"]))
' "$file")

if [ "$count" -lt "$MIN_VECTORS" ]; then
  echo "FAIL  $file yielded $count vector(s), floor $MIN_VECTORS." >&2
  echo "      If the file still holds one object per vector, VECTORS are what shrank and somebody" >&2
  echo "      deleted one. If it does not, THIS READER is what broke, and a reader that parses" >&2
  echo "      nothing reads exactly like a table with nothing to check." >&2
  exit 1
fi

fail=0
for i in $(seq 0 $((count - 1))); do
  name=$(python3 -c '
import json,sys
print(json.load(open(sys.argv[1]))["vectors"][int(sys.argv[2])]["name"])
' "$file" "$i")
  want=$(python3 -c '
import json,sys
print(json.load(open(sys.argv[1]))["vectors"][int(sys.argv[2])]["digest"])
' "$file" "$i")

  if ! printf '%s' "$want" | grep -Eq '^[0-9a-f]{12}$'; then
    echo "FAIL  $name: recorded digest '$want' is not 12 lower-case hex." >&2
    echo "      The rule is the first 12 hex of sha256. A width change is exactly what this table is for." >&2
    fail=1
    continue
  fi

  # The bytes go to sha256sum on a pipe. Python decodes the JSON string and
  # writes UTF-8; it never hashes.
  got=$(python3 -c '
import json,sys
sys.stdout.buffer.write(json.load(open(sys.argv[1]))["vectors"][int(sys.argv[2])]["english"].encode("utf-8"))
' "$file" "$i" | sha256sum | cut -c1-12)

  if [ "$got" != "$want" ]; then
    echo "FAIL  $name: recorded $want, sha256sum says $got" >&2
    fail=1
  fi
done

# The pairs. Each is one normalisation somebody could add to one side of the
# coupling; if the two halves ever hash the same, the vector that was supposed
# to catch it has quietly stopped being able to.
pairs="lf:crlf case-upper:case-lower nfc-e-acute:nfd-e-acute nfc-short-i:nfd-short-i empty:single-space"
for p in $pairs; do
  a="${p%%:*}"
  b="${p##*:}"
  if ! python3 -c '
import json,sys
vs={v["name"]: v for v in json.load(open(sys.argv[1]))["vectors"]}
a,b=sys.argv[2],sys.argv[3]
for n in (a,b):
    if n not in vs:
        print(f"MISSING {n}"); sys.exit(2)
sys.exit(0 if vs[a]["digest"] != vs[b]["digest"] else 3)
' "$file" "$a" "$b"; then
    echo "FAIL  the pair $a / $b does not differ, or one of them is gone." >&2
    echo "      That pair exists because a normalisation added to one implementation would make" >&2
    echo "      them equal. Two halves that already collide catch nothing." >&2
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "FAIL  digest-vectors.json does not agree with coreutils." >&2
  exit 1
fi

echo "ok    $count locale digest vector(s) re-derived with sha256sum; 5 non-collision pair(s) hold"

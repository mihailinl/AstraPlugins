#!/usr/bin/env bash
# The fourth implementation.
#
# Three programs re-derive these digests: the CLI's packer (sha2), the daemon's
# reader (sha2), and the registry bot (node's crypto). Two of those three share
# a SHA-256 implementation, and all three were written from the same notes — so
# "all three agree" is a weaker statement than it looks. If the notes are wrong,
# or if the domain prefix is spelt the same wrong way in each, they agree
# perfectly on an answer nobody else can reproduce.
#
# This script computes the same two numbers with coreutils and nothing else:
#
#   artifact digest = sha256sum <file>
#   manifest digest = sha256sum of ("astra.bundle/2\0" ‖ the bytes dd carves
#                     out of the local file header at offset 0)
#
# `dd`, `od`, `printf`, `cat`, `sha256sum`. No node, no cargo, no library of
# ours anywhere in the path. Compare its output to `vectors.json` and the claim
# stops being self-referential.
#
#   ./testdata/bundles/handcheck.sh            # check every vector
#   ./testdata/bundles/handcheck.sh ok-minimal # one, with the working shown
#
# Vectors whose entry zero is not a STORED `MANIFEST.json` are skipped for the
# manifest digest and named as skips — carving a deflate stream out of
# `manifest-compressed` would hash the compressed bytes, which is not what the
# digest is over.

set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

# The ZIP local file header, the only part of the format this script knows:
#   0  signature (PK\3\4)      8  compression method
#   18 compressed size        26  file name length
#   28 extra field length     30  file name
LOCAL_METHOD_OFF=8
LOCAL_CSIZE_OFF=18
LOCAL_NAMELEN_OFF=26
LOCAL_EXTRALEN_OFF=28
LOCAL_HEADER_LEN=30

# Read a little-endian unsigned integer of `n` bytes at `off`.
le() { # file off n
  od -An -tu"$3" -j"$2" -N"$3" --endian=little "$1" | tr -d ' \n'
}

read_str() { # file off len
  dd if="$1" bs=1 skip="$2" count="$3" status=none
}

sha() { sha256sum | cut -d' ' -f1; }

only="${1:-}"
fail=0
checked=0
skipped=0
verbose=0
[ -n "$only" ] && verbose=1

for f in *.astraplugin; do
  name="${f%.astraplugin}"
  [ -n "$only" ] && [ "$name" != "$only" ] && continue

  artifact="$(sha256sum "$f" | cut -d' ' -f1)"

  method="$(le "$f" $LOCAL_METHOD_OFF 2)"
  namelen="$(le "$f" $LOCAL_NAMELEN_OFF 2)"
  extralen="$(le "$f" $LOCAL_EXTRALEN_OFF 2)"
  csize="$(le "$f" $LOCAL_CSIZE_OFF 4)"
  entry0="$(read_str "$f" $LOCAL_HEADER_LEN "$namelen")"

  manifest_digest="-"
  manifest_sha="-"
  if [ "$entry0" = "MANIFEST.json" ] && [ "$method" = "0" ]; then
    start=$(( LOCAL_HEADER_LEN + namelen + extralen ))
    tmp="$(mktemp)"
    dd if="$f" bs=1 skip="$start" count="$csize" status=none > "$tmp"
    manifest_sha="$(sha < "$tmp")"
    # "astra.bundle/2" then one NUL byte, then the manifest, hashed as one
    # stream. `printf '\0'` is the domain separator, written out where it can
    # be read rather than hidden behind a constant in three languages.
    manifest_digest="$( { printf 'astra.bundle/2'; printf '\0'; cat "$tmp"; } | sha )"
    if [ "$verbose" = 1 ]; then
      echo "  entry 0        : $entry0 (method $method, $csize bytes at offset $start)"
      echo "  sha256(manifest bytes)                  = $manifest_sha"
      echo "  sha256(\"astra.bundle/2\\0\" || manifest) = $manifest_digest"
    fi
    rm -f "$tmp"
    checked=$(( checked + 1 ))
  else
    skipped=$(( skipped + 1 ))
  fi

  printf '%s  %s  %s\n' "$artifact" "$manifest_digest" "$f"
done

if [ -z "$only" ]; then
  echo "# $checked manifest digests carved from the local header at offset 0, $skipped skipped"
  echo "# columns: artifact_sha256  manifest_digest  file"
  echo "# compare against vectors.json — the numbers must be identical"
fi
exit $fail

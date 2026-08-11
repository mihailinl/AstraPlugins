# Publishing — moved

The old page at this path told authors to compare a `PUBKEY` the daemon
discards, documented an RPC that takes a directory as one that takes bytes,
called the registry "planned" when its client had already shipped, promised a
revocation channel that did not exist, and presented sideloading as the normal
way to install a plugin. It has been deleted rather than corrected.

**The publishing path is now four pages:**

- [Release with CI](5-publish/release-with-ci.md) — `astra-plugin init-ci`, then a tag
- [Get listed](5-publish/get-listed.md) — one submission, once, ever
- [Install a local file](5-publish/local-install.md) — advanced, and what it costs
- [Sideload a source directory](5-publish/sideload.md) — a developer tool, not an install path

## What establishes trust

`astra-plugin build` links here, so the answer lives at this anchor until that
link moves.

**Not any key you hold.** `astra-plugin keygen` and `astra-plugin sign` produce
an optional second factor — useful against a GitHub account takeover, because
the key lives somewhere a stolen GitHub session is not. Astra does not verify
it against your key: the daemon checks the in-ZIP `SIGNATURE`/`PUBKEY` pair
against a *pinned Astra publisher key*, so a bundle signed with your own key is
untrusted in exactly the way an unsigned one is. Both the command and the format
entries it writes are being retired.

**What Astra actually acts on** is a registry record that countersigns the
SHA-256 of the whole file, and — checked by the registry bot at ingest, not by
the daemon — GitHub's build attestation saying which workflow, at which commit,
in which repository produced those bytes.

**And today, none of that is anchored.** The root keys now exist — `root.json`
lists the same two the daemon compiles in — but the root-signed `trust.json`
that delegates to an index-signing key does not, so the daemon has no key to
check a catalogue signature against. Every catalogue classifies as unsigned and
the daemon fails closed. See [the security model](1-orientation/security.md) and
[`spec/registry-index.md` §0.1](spec/registry-index.md).

**None of it says the code is safe.** A plugin is a native process with your
full user privileges; there is no sandbox.

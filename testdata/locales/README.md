# The shared locale rule corpus

One directory of plugin fixtures with the verdict written down beside each one,
read by **two implementations of one rule set**: `astra-plugin check` /
`astra-plugin build` in this repository, and — when batch 6 lands it —
`bot/lib/locales.mjs` in `astra-registry`.

That is coupling **C16**, and it is the coupling with the worst failure shape in
this project. The CLI refuses a bundle *before* a tag is pushed. The bot refuses
a listing *after* one is. If the two disagree, an author's release passes every
gate they can see and dies in a repository they have never opened, on a rule
they were never shown — or, worse in the other direction, a bundle the CLI
waved through is published with a locale file nothing can select.

Neither half can be tested against the other directly: one is Rust and one is
JavaScript, and they run in different repositories at different moments in a
release. A corpus is what they can both be tested against.

## Layout

```
pass/<case>/     plugin.toml [+ locales/…] [+ locales.lock.json]  and WHY
fail/<case>/     the same, plus EXPECT
```

* **`WHY`** — prose, for a human. What this case is about and what it costs when
  the rule is not there. Read by nobody; write it anyway, because a fixture
  whose point is not written down is a fixture the next person deletes.
* **`EXPECT`** — one rule id per line. **The set of ERROR ids the case must
  produce, exactly** — not a subset, and not "at least these". Notes are not
  constrained: a case is allowed to emit any number of them, because notes are
  advice and advice is allowed to grow.

A `pass/` case has no `EXPECT` and must produce **no errors at all**.

## The contract a second implementation is held to

1. Read `plugin.toml` and, if it is there, `locales/*.json` and
   `locales.lock.json`, from the case directory.
2. Run the rules at **check severity** — the gate that does *not* promote N2 and
   N3, and that permits `qps`. The build gate's three promotions are exercised
   by each implementation's own unit tests, because a corpus case cannot carry
   two verdicts.
3. Compare the set of error ids with `EXPECT`.

## The floor, and why it is written before the mutation

Every reader of this corpus **asserts a minimum number of cases loaded, and does
it before it asserts anything about any of them.** An absent corpus, a
`sparse-checkout` that does not include this directory, a glob that stopped
matching, a rename — all four produce a reader that enumerates nothing, and an
empty enumeration passes for the wrong reason: quietly, for ever, while reading
as coverage.

The floor's own failure message must distinguish the two things that can break:
*the rule changed* and *the scan changed*. They need opposite fixes and they
look identical from a green tick.

`astra-registry`'s `build-index.yml` checks this repository out with
`sparse-checkout: spec`. **It has to gain `testdata/locales` before its half of
C16 can run at all**, and until it does, its reader must print that it did not
run rather than reporting a clean corpus it never opened.

**It gained it.** `astra-registry/.github/workflows/build-index.yml` now checks
this repository out at the manifest pin with `sparse-checkout: spec` *and*
`testdata/locales`, into `_astra-plugins`, and hands it to `tools/validate.mjs`
as `$ASTRA_PLUGINS_DIR` — on every push to `main` and every pull request. That
step turns any `NOT verified` line in the validator's output into an `::error::`
and `exit 1`, so a checkout that silently did not arrive stops the catalogue
deploying rather than reading as a clean corpus. The paragraph above is kept
because it is why the sparse-checkout gained a second entry, and because the
state it describes is the one this page exists to make impossible.

## `digest-vectors.json` — the lock digest, held to coreutils

A second corpus in this directory, with a different shape and a different job.
The cases above are **trees with verdicts**; this file is a flat table of
**inputs with numbers**, and it exists because the rule it is about cannot be
written as a case.

`locales.lock.json` records, per translated key, the first 12 hex of sha256 over
the English bytes that translation was made against. `astra-plugin locale sync`
**writes** those digests — `digest` in
`astra-plugin-cli/src/commands/locale.rs`. `bot/lib/locales.mjs` in
astra-registry **reads** them — `englishDigest`. That is coupling **C19**, and
until this file **nothing had ever compared the two**: they were run against the
same English once and produced the same values, which is agreement by luck.

**Why the cases above cannot do it.** Staleness is a NOTE on the CLI's side and
a WARNING on the registry's, and both readers of that corpus compare **error id
sets** and nothing else. A case whose lock is deliberately one hash behind
therefore proves that both sides stayed *quiet* — never that both sides computed
the *same number*. `pass/plural-families` ships digests that deliberately match
no English in it, which is exactly what pins that note as a note, and is the
clearest statement available that these cases are not the instrument for C19.

**The table was written by neither implementation.** Every `digest` in it is
what coreutils `sha256sum` returns for the vector's exact UTF-8 bytes;
`digest-handcheck.sh` re-derives all of them that way and CI runs it. Two
programs that share a mistake can agree with each other; they cannot agree with
coreutils. `testdata/bundles/handcheck.sh` makes the same argument about the
bundle digests, and `tests/shared-vectors.mjs` in astra-registry repeats it.

**Read by:**

| | |
|---|---|
| `astra-plugin-cli/src/commands/locale_tests.rs` | `the_lock_digest_agrees_with_a_table_neither_implementation_wrote` |
| `astra-registry/tools/validate.mjs` | `checkLocaleDigestVectors`, over the `testdata/locales` checkout `build-index.yml` already fetches |
| `testdata/locales/digest-handcheck.sh` | the derivation itself, with `sha256sum` |

Each reader asserts a **floor** on the vectors it loaded before it compares any
of them, for the reason the floor above exists.

**The file is 7-bit ASCII on purpose** — every non-ASCII character is a `\uXXXX`
escape. Unicode normalisation is one of the two failures the table is for, and a
vector an editor, a transfer or a merge tool can silently renormalise is a
vector that has stopped testing what it says it tests.

**Five pairs must not collide** — `lf`/`crlf`, `case-upper`/`case-lower`,
`nfc-e-acute`/`nfd-e-acute`, `nfc-short-i`/`nfd-short-i`, `empty`/`single-space`.
Each is one normalisation somebody could add to one side of the coupling. A
per-vector comparison cannot see a pair that has *already* collided, so all three
readers assert the pairs separately.

The first four vectors are the four English strings `pass/lock-up-to-date`'s
committed lock is keyed on, so the two corpora in this directory meet on a
number rather than on an assumption.

## Adding a case

Add the directory, write `WHY`, write `EXPECT` if it fails — and then **break
the rule on purpose and watch the new case go red**, because a fixture that has
never failed is a fixture that might be asserting nothing. If a rule cannot be
given a fixture, it goes on the reader's exemption list with a sentence saying
why; an exemption is a visible blank, and an absence is not.

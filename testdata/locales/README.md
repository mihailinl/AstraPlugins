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

## Adding a case

Add the directory, write `WHY`, write `EXPECT` if it fails — and then **break
the rule on purpose and watch the new case go red**, because a fixture that has
never failed is a fixture that might be asserting nothing. If a rule cannot be
given a fixture, it goes on the reader's exemption list with a sentence saying
why; an exemption is a visible blank, and an absence is not.

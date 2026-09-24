//! The binding line: `astra-binding: <token>` in `.well-known/astra-plugin-owner`.
//!
//! One reader and one writer, and both are somebody else's rules.
//!
//! * **The reader** is contract ID-23 and ID-24, the rules astra-registry's bot
//!   applies at the attested commit (`bot/lib/binding.mjs`) and the plugins
//!   service applies to the default branch. `astra-plugin check` runs it so an
//!   author learns `B_BINDING_MALFORMED` before a tag rather than after one —
//!   and it has to be *the same* reader, not a similar one: a CLI laxer than the
//!   bot tells an author their tag is fine and the refusal arrives at ingest; a
//!   CLI stricter than the bot refuses a repository that is bound correctly.
//! * **The writer** is FLOW-49 and FLOW-50: `init-ci --binding <token>` writes
//!   exactly one line, first, and removes every line ID-24 would count.
//!
//! Neither is tested against itself. `testdata/binding-line/vectors.json` is
//! astra-registry's corpus, mirrored byte for byte (C31), and this module's
//! tests run every case in it — after verifying the corpus's `SHA256SUMS`, so
//! a walk that lost its file cannot find no disagreement and pass.
//!
//! # Three decisions that are not accidents
//!
//! * **The window is BYTES of the file as delivered.** Not characters. 1400
//!   three-byte characters are 4200 bytes; a line after them is outside
//!   ID-23's window even though a character count says it is inside (vector 15).
//! * **The grammar is matched over bytes.** Every character ID-23 names is
//!   ASCII. Decoding UTF-8 first would replace an invalid byte by U+FFFD —
//!   three bytes where one stood — and move every later line rightwards
//!   (vector 20), and it invites normalising `Astra-Binding` into a match.
//! * **Nothing a stranger wrote is echoed back.** A finding names the rule and
//!   the line number, never the line. The token is public (DEC-2) and is the
//!   one exception, quoted only after it matched `[A-Za-z0-9_-]{16,128}`.
//!
//! # What this module does NOT decide
//!
//! **It never answers `B_UNBOUND`.** "No line here" and "this listing needed
//! one" are different questions; the second is the registry's, keyed on the
//! binding deadline and the listing's history. `check` reports a missing line
//! as a *prediction* of `B_UNBOUND`, which is the most this side can know.
//! Whether a token is bound, whose it is, and whether that account may publish
//! are the service's, and `check` says it did not check them (FLOW-52).
//!
//! The five questions the contract has not answered (Q1–Q5: the window's edge,
//! near-misses outside it, `\r\r`, a BOM not at the start, and what the service
//! reads) are answered here exactly as the corpus's `proposals` member answers
//! them, which is how the bot answers them — `MBE-PENDING` upstream, one
//! answer on both sides of it here.

/// ID-23's window, in bytes of the file as delivered. A leading BOM occupies
/// three of them: the window is what was read.
pub const WINDOW_BYTES: usize = 4096;

/// ID-23, verbatim as the contract writes it. Not executed — this crate has no
/// regex engine and does not need one for a grammar this small — but carried
/// as a string so the tests can hold [`recognise`] to the corpus's own
/// `grammar.id_23` member, the way the bot's suite holds its copy.
// Read by the tests, against the corpus's own `grammar` member.
#[cfg_attr(not(test), allow(dead_code))]
pub const ID_23_SOURCE: &str = r"^[ \t]*astra-binding:[ \t]*([A-Za-z0-9_-]{16,128})[ \t]*(#.*)?$";

/// ID-24's near-miss prefix, case-insensitive. The colon is required, which
/// is what keeps a bare `astra-binding` a GitHub login (vector 26).
// Read by the tests, against the corpus's own `grammar` member.
#[cfg_attr(not(test), allow(dead_code))]
pub const ID_24_PREFIX_SOURCE: &str = r"^[ \t]*astra-binding[ \t]*:";

/// FLOW-50's MINTED grammar. Deliberately narrower than ID-23's `{16,128}`:
/// the registry must go on recognising a line an older tool or a person wrote,
/// and this CLI must not write anything a 128-bit CSPRNG would not produce.
// Read by the tests, against the corpus's own `grammar` member.
#[cfg_attr(not(test), allow(dead_code))]
pub const CLI_WRITE_SOURCE: &str = r"^[A-Za-z0-9_-]{22,128}$";

/// The file, relative to the repository root. ID-22: the root, whatever
/// `plugin-dir` says.
pub const OWNER_FILE: &str = ".well-known/astra-plugin-owner";

/// What the reader concluded. `B_UNBOUND` is not one of these; see the module
/// docs.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Outcome {
    /// No ID-23 line and no ID-24 near miss inside the window.
    None,
    /// Exactly one ID-23 line, and no near miss.
    One { token: String, line: usize },
    /// `B_BINDING_MALFORMED`: more than one line, or a near miss.
    Malformed { reason: String },
}

impl Outcome {
    /// The corpus's word for this outcome.
    pub fn word(&self) -> &'static str {
        match self {
            Outcome::None => "none",
            Outcome::One { .. } => "one",
            Outcome::Malformed { .. } => "malformed",
        }
    }
}

fn is_token_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'-' || b == b'_'
}

fn skip_blanks(line: &[u8], mut i: usize) -> usize {
    while i < line.len() && (line[i] == b' ' || line[i] == b'\t') {
        i += 1;
    }
    i
}

/// ID-23 over one line's bytes (no `\n`, one trailing `\r` already removed).
///
/// Every quantifier in the pattern is over a class disjoint from what follows
/// it, so the match is deterministic and this is the whole of it: blanks, the
/// literal, blanks, the longest run of token bytes, blanks, then the end or a
/// `#` followed by anything but `\r` — JavaScript's `.` refuses `\r`, which is
/// why `\r\r\n` is malformed (Q3, vector 6).
pub fn recognise(line: &[u8]) -> Option<String> {
    const LIT: &[u8] = b"astra-binding:";
    let i = skip_blanks(line, 0);
    let rest = line.get(i..)?;
    if !rest.starts_with(LIT) {
        return None;
    }
    let start = skip_blanks(line, i + LIT.len());
    let mut end = start;
    while end < line.len() && is_token_byte(line[end]) {
        end += 1;
    }
    let len = end - start;
    if !(16..=128).contains(&len) {
        return None;
    }
    let after = skip_blanks(line, end);
    if after == line.len() {
        return Some(String::from_utf8_lossy(&line[start..end]).into_owned());
    }
    if line[after] == b'#' && !line[after..].iter().any(|&b| b == b'\r' || b == b'\n') {
        return Some(String::from_utf8_lossy(&line[start..end]).into_owned());
    }
    None
}

/// ID-24's prefix, ASCII case-insensitively. JavaScript's `/i` without `/u`
/// never folds a non-ASCII character onto an ASCII one, so ASCII folding is the
/// bot's rule exactly.
pub fn near_miss_prefix(line: &[u8]) -> bool {
    const LIT: &[u8] = b"astra-binding";
    let i = skip_blanks(line, 0);
    let Some(word) = line.get(i..i + LIT.len()) else {
        return false;
    };
    if !word.eq_ignore_ascii_case(LIT) {
        return false;
    }
    let j = skip_blanks(line, i + LIT.len());
    line.get(j) == Some(&b':')
}

/// Would `init-ci --binding` write this token? FLOW-50.
pub fn cli_accepts(token: &str) -> bool {
    (22..=128).contains(&token.len()) && token.bytes().all(is_token_byte)
}

/// ID-23 and ID-24 over one file's bytes, as the bot parses them.
pub fn parse(file: &[u8]) -> Outcome {
    let head = &file[..file.len().min(WINDOW_BYTES)];
    // The file ran past the window, so its last in-window line has no
    // terminator the reader may believe in (vectors 12, 13).
    let truncated = file.len() > WINDOW_BYTES;
    // Q4: a BOM is ignored only at the start of the file.
    let mut i = if head.starts_with(&[0xEF, 0xBB, 0xBF]) { 3 } else { 0 };

    let mut matches: Vec<(usize, String)> = Vec::new();
    let mut candidates: Vec<usize> = Vec::new();
    let mut lineno = 0usize;
    while i < head.len() {
        let end = match head[i..].iter().position(|&b| b == b'\n') {
            Some(off) => i + off,
            // No `\n` before byte 4096: the file's last line if the FILE ended
            // inside the window, a line crossing the boundary if it did not.
            None if truncated => break,
            None => head.len(),
        };
        lineno += 1;
        let mut line_end = end;
        // "minus one `\r`" — exactly one.
        if line_end > i && head[line_end - 1] == b'\r' {
            line_end -= 1;
        }
        let line = &head[i..line_end];
        if let Some(token) = recognise(line) {
            matches.push((lineno, token));
        } else if near_miss_prefix(line) {
            candidates.push(lineno);
        }
        if end == head.len() {
            break;
        }
        i = end + 1;
    }

    // A near miss BESIDE a good line still refuses: the file says two things
    // about who owns the repository, and picking the one that parses is how a
    // reader gets chosen for by whoever wrote the file.
    if !candidates.is_empty() || matches.len() > 1 {
        let reason = if matches.len() > 1 {
            let lines: Vec<String> = matches.iter().map(|(l, _)| l.to_string()).collect();
            format!(
                "{} binding lines inside the first {WINDOW_BYTES} bytes (lines {}). Exactly one \
                 line counts (ID-24), and choosing between two is not a thing a parser may do",
                matches.len(),
                lines.join(", ")
            )
        } else {
            let lines: Vec<String> = candidates.iter().map(|l| l.to_string()).collect();
            format!(
                "line {} of {OWNER_FILE} begins `astra-binding` and a colon and does not match \
                 ID-23 — a line somebody meant as a binding (ID-24){}",
                lines.join(", line "),
                if matches.len() == 1 {
                    ", beside a well-formed one"
                } else {
                    ""
                }
            )
        };
        return Outcome::Malformed { reason };
    }
    match matches.pop() {
        Some((line, token)) => Outcome::One { token, line },
        None => Outcome::None,
    }
}

/// FLOW-49: the owner file with exactly one binding line for `token`, first.
///
/// Every line ID-24 would count — any case of `astra-binding` then a colon,
/// anywhere in the file and not only inside the window — is removed; every
/// other line is kept byte for byte, its own line ending included. A leading
/// BOM is dropped rather than pushed onto the second line, where it would stop
/// being ignored (Q4) and turn a login line into a line that matches nothing.
///
/// The caller has already checked [`cli_accepts`]; this refuses again rather
/// than write a line the reader would call malformed.
pub fn rewrite(existing: &[u8], token: &str) -> Result<Vec<u8>, String> {
    if !cli_accepts(token) {
        return Err(refusal(token));
    }
    let body = existing.strip_prefix(&[0xEF, 0xBB, 0xBF][..]).unwrap_or(existing);
    let mut out = format!("astra-binding: {token}\n").into_bytes();
    if !body.is_empty() {
        for piece in body.split_inclusive(|&b| b == b'\n') {
            let mut text = piece.strip_suffix(b"\n").unwrap_or(piece);
            text = text.strip_suffix(b"\r").unwrap_or(text);
            if near_miss_prefix(text) {
                continue;
            }
            out.extend_from_slice(piece);
        }
    }
    // The line just written must read back as exactly this token. It always
    // does — it is first, and every competitor was removed — and asserting it
    // costs nothing next to shipping a writer the reader disagrees with.
    match parse(&out) {
        Outcome::One { token: t, .. } if t == token => Ok(out),
        other => Err(format!(
            "the rewritten owner file reads back as `{}`, not as this token — refusing to write it",
            other.word()
        )),
    }
}

/// Why `--binding` refused a value, without echoing it: it is the author's own
/// input, and a string that failed the grammar is exactly the one not to print.
pub fn refusal(token: &str) -> String {
    let len = token.len();
    let bad = token.bytes().filter(|&b| !is_token_byte(b)).count();
    let why = if bad > 0 {
        format!("{bad} character(s) outside `[A-Za-z0-9_-]`")
    } else if len < 22 {
        format!("{len} characters; a minted token is at least 22")
    } else {
        format!("{len} characters; a minted token is at most 128")
    };
    format!(
        "--binding takes the token the panel minted, `[A-Za-z0-9_-]{{22,128}}` (FLOW-50), and \
         this one has {why}. Copy it again from the panel's mint page; nothing was written."
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::Engine;
    use sha2::{Digest, Sha256};
    use std::path::PathBuf;

    fn corpus_dir() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../testdata/binding-line")
    }

    /// `vectors.json`, after its `SHA256SUMS` line has been checked. A corpus
    /// that went missing or was edited must be a red test, never a walk over
    /// nothing.
    fn corpus() -> serde_json::Value {
        let dir = corpus_dir();
        let bytes = std::fs::read(dir.join("vectors.json")).expect(
            "testdata/binding-line/vectors.json is missing — it is astra-registry's corpus, \
             mirrored here by C31; this suite refuses to pass without it",
        );
        let sums = std::fs::read_to_string(dir.join("SHA256SUMS")).expect("SHA256SUMS is missing");
        let want = sums
            .lines()
            .find_map(|l| l.strip_suffix("vectors.json").map(|h| h.trim().trim_end_matches('*').trim().to_string()))
            .expect("SHA256SUMS has no line for vectors.json");
        let got: String = Sha256::digest(&bytes).iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(got, want, "vectors.json does not hash to SHA256SUMS: the copy was edited");
        serde_json::from_slice(&bytes).expect("vectors.json is not JSON")
    }

    fn cases(c: &serde_json::Value) -> Vec<serde_json::Value> {
        c["cases"].as_array().expect("no `cases` array").clone()
    }

    #[test]
    fn every_corpus_case_reads_as_the_registry_reads_it() {
        let c = corpus();
        let cases = cases(&c);
        let floor_cases = c["floors"]["cases"].as_u64().expect("no floors.cases") as usize;
        let floor_vectors = c["floors"]["vectors"].as_u64().expect("no floors.vectors") as usize;
        let vectors: std::collections::BTreeSet<u64> =
            cases.iter().filter_map(|k| k["vector"].as_u64()).collect();
        assert!(
            cases.len() >= floor_cases && vectors.len() >= floor_vectors,
            "{} case(s) over {} vector(s); the corpus's own floors are {floor_cases} and \
             {floor_vectors}",
            cases.len(),
            vectors.len()
        );
        let mut wrong = Vec::new();
        for case in &cases {
            let name = case["case"].as_str().unwrap_or("?");
            let file = base64::engine::general_purpose::STANDARD
                .decode(case["file_b64"].as_str().expect("file_b64"))
                .expect("file_b64 is not base64");
            assert_eq!(file.len() as u64, case["bytes"].as_u64().unwrap(), "{name}: byte count");
            let got = parse(&file);
            let want = case["outcome"].as_str().unwrap();
            let want_token = case["token"].as_str();
            let got_token = match &got {
                Outcome::One { token, .. } => Some(token.as_str()),
                _ => None,
            };
            if got.word() != want || got_token != want_token {
                wrong.push(format!(
                    "{name}: the registry says {want} {want_token:?}, this reader says {} {got_token:?}",
                    got.word()
                ));
            }
        }
        assert!(wrong.is_empty(), "{} case(s) disagree:\n{}", wrong.len(), wrong.join("\n"));
    }

    /// The `cli_write` column is FLOW-50's writer against ID-23's reader, and
    /// a column no program computes is a column somebody typed. The bot
    /// computes it from its copy of the grammar; this computes it from ours.
    #[test]
    fn the_writer_refuses_exactly_the_tokens_the_corpus_says_it_refuses() {
        let c = corpus();
        let mut checked = 0;
        for case in cases(&c) {
            let Some(token) = case["token"].as_str() else {
                continue;
            };
            checked += 1;
            let refuse = case["cli_write"].as_str() == Some("refuse");
            assert_eq!(
                cli_accepts(token),
                !refuse,
                "{}: FLOW-50 {} a {}-character token",
                case["case"],
                if refuse { "refuses" } else { "accepts" },
                token.len()
            );
        }
        assert!(checked >= 10, "only {checked} case(s) carry a token");
    }

    #[test]
    fn the_grammar_strings_are_the_corpus_s() {
        let c = corpus();
        assert_eq!(c["grammar"]["id_23"].as_str(), Some(ID_23_SOURCE));
        assert_eq!(c["grammar"]["id_24_prefix"].as_str(), Some(ID_24_PREFIX_SOURCE));
        assert_eq!(c["grammar"]["cli_write"].as_str(), Some(CLI_WRITE_SOURCE));
        assert_eq!(c["window_bytes"].as_u64(), Some(WINDOW_BYTES as u64));
        assert_eq!(c["window_unit"].as_str(), Some("bytes"));
    }

    const TOKEN: &str = "abcdefghijklmnopqrstuvwxyzABCDEF";

    #[test]
    fn a_case_variant_line_past_byte_4096_in_a_5000_byte_file_is_removed() {
        // FLOW-49 removes EVERY line ID-24 would count, not only those inside
        // the window: a leftover near miss past 4096 is harmless to ID-23
        // today, and becomes `B_BINDING_MALFORMED` the day an earlier line is
        // deleted and it slides inside.
        let mut file = b"some-login\n".to_vec();
        while file.len() < 4300 {
            file.extend_from_slice(b"# padding line, kept byte for byte by the writer\n");
        }
        let stale = b"Astra-Binding : zzzzzzzzzzzzzzzzzzzzzzzzzzzz\n";
        file.extend_from_slice(stale);
        while file.len() < 5000 {
            file.extend_from_slice(b"x");
        }
        assert_eq!(file.len(), 5000);
        assert!(file.windows(stale.len()).position(|w| w == stale).unwrap() > WINDOW_BYTES);
        let out = rewrite(&file, TOKEN).unwrap();
        assert!(out.starts_with(format!("astra-binding: {TOKEN}\nsome-login\n").as_bytes()));
        assert!(
            !out.windows(13).any(|w| w.eq_ignore_ascii_case(b"astra-binding") && w != b"astra-binding"),
            "the case-variant line past byte 4096 survived the rewrite"
        );
        assert_eq!(out.len(), 5000 - stale.len() + format!("astra-binding: {TOKEN}\n").len());
        assert_eq!(parse(&out), Outcome::One { token: TOKEN.into(), line: 1 });
    }

    #[test]
    fn the_writer_keeps_every_other_line_and_its_line_ending() {
        let file = b"\xEF\xBB\xBFowner-login\r\nastra-binding: oldoldoldoldoldoldoldold\r\n  ASTRA-BINDING:x\nastra-binding\nlast";
        let out = rewrite(file, TOKEN).unwrap();
        assert_eq!(
            out,
            format!("astra-binding: {TOKEN}\nowner-login\r\nastra-binding\nlast").into_bytes(),
            "a bare `astra-binding` is a login (vector 26) and stays; the BOM goes rather than \
             moving onto line 2, where Q4 stops ignoring it"
        );
    }

    #[test]
    fn the_writer_refuses_what_flow_50_refuses_and_says_so_without_echoing_it() {
        for bad in ["abcdefghijklmnopqrstu", "abc+defghijklmnopqrstuvwxyz", &"a".repeat(129)] {
            let e = rewrite(b"", bad).unwrap_err();
            assert!(e.contains("FLOW-50"), "{e}");
            assert!(!e.contains(bad), "the refusal echoed the value it refused: {e}");
        }
        assert!(rewrite(b"", &"a".repeat(22)).is_ok());
        assert!(rewrite(b"", &"a".repeat(128)).is_ok());
    }
}

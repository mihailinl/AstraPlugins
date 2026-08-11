//! One output discipline for every subcommand: `--json`, and exit codes that
//! mean something.
//!
//! # Exit codes
//!
//! Three, and the split is the one a script needs:
//!
//! | code | meaning | example |
//! |---|---|---|
//! | 0 | the answer is yes | `check` found no errors |
//! | 1 | **the artefact is wrong** | `check` found errors, `test` saw an `UNIMPLEMENTED`, `verify` saw a bad digest |
//! | 2 | **the CLI could not answer** | no `plugin.toml`, `cargo build` failed, the daemon is not running, a bad flag |
//!
//! The distinction is the whole point. A release workflow that treats every
//! non-zero exit the same cannot tell "your plugin is broken" from "the
//! toolchain is missing", and both used to be exit 1 here.
//!
//! [`Rejected`] is how a command says 1. Everything else — every `?`, every
//! `anyhow::bail!` — is 2. That default is deliberate: an error nobody
//! classified is an error nobody thought about, and calling it "the artefact is
//! fine, the tool broke" is the safe direction to be wrong in.
//!
//! # `--json`
//!
//! Every subcommand takes it. In JSON mode a command prints **exactly one**
//! JSON document to stdout and nothing else, so `astra-plugin … --json | jq`
//! works without the caller filtering progress chatter. Human progress lines
//! therefore go through [`hprintln!`], which is a no-op in JSON mode, and
//! diagnostics that are not part of the document go to stderr.
//!
//! Every document carries the same three keys, so a caller can branch before it
//! knows the command:
//!
//! ```json
//! { "command": "check", "ok": false, "exit_code": 1, … }
//! ```

use std::sync::atomic::{AtomicBool, Ordering};

use serde_json::{Value, json};

static JSON: AtomicBool = AtomicBool::new(false);

/// Turn JSON mode on. Called once, from `main`, before anything prints.
pub fn set_json(on: bool) {
    JSON.store(on, Ordering::Relaxed);
}

/// Whether this run must print one JSON document and nothing else.
pub fn json_mode() -> bool {
    JSON.load(Ordering::Relaxed)
}

/// `println!`, unless `--json` is in force.
///
/// Progress and prose go through this. A `println!` that survives in JSON mode
/// is a bug: it corrupts the document for every caller that pipes us.
#[macro_export]
macro_rules! hprintln {
    () => {
        if !$crate::output::json_mode() { println!() }
    };
    ($($arg:tt)*) => {
        if !$crate::output::json_mode() { println!($($arg)*) }
    };
}

/// Print the one document, if `--json` is in force.
///
/// `command`, `ok` and `exit_code` are stamped here rather than at each call
/// site so they cannot disagree with the process's real exit status.
pub fn emit(command: &str, verdict: &Verdict, mut body: Value) {
    if !json_mode() {
        return;
    }
    let obj = body.as_object_mut().expect("emit() takes a JSON object");
    obj.insert("command".into(), json!(command));
    obj.insert("ok".into(), json!(verdict.is_pass()));
    obj.insert("exit_code".into(), json!(verdict.code()));
    println!("{}", serde_json::to_string_pretty(&body).unwrap_or_default());
}

/// What a command decided. Returned rather than printed, so `main` owns the
/// process's exit status in one place.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    /// Exit 0.
    Pass,
    /// Exit 1 — the thing under inspection is wrong.
    Fail,
}

impl Verdict {
    pub fn is_pass(self) -> bool {
        matches!(self, Verdict::Pass)
    }

    pub fn code(self) -> i32 {
        match self {
            Verdict::Pass => 0,
            Verdict::Fail => 1,
        }
    }

    /// `Pass` when `ok`, `Fail` otherwise.
    pub fn of(ok: bool) -> Self {
        if ok { Verdict::Pass } else { Verdict::Fail }
    }
}

/// The error a command returns when **the artefact is wrong** rather than the
/// tool.
///
/// It exists so that exit 1 is a decision a command makes on purpose. Wrap it
/// in `anyhow` freely — `main` downcasts through the chain, so
/// `.context("while checking")?` keeps the classification.
#[derive(Debug)]
pub struct Rejected(pub String);

impl Rejected {
    pub fn new(message: impl Into<String>) -> Self {
        Self(message.into())
    }

    /// `Rejected` as an `anyhow::Error`, for `return Err(...)`.
    pub fn err(message: impl Into<String>) -> anyhow::Error {
        anyhow::Error::new(Self::new(message))
    }
}

impl std::fmt::Display for Rejected {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Rejected {}

/// The exit code an error maps to: 1 if any link in the chain is a
/// [`Rejected`], else 2.
pub fn code_for(err: &anyhow::Error) -> i32 {
    if err.chain().any(|e| e.is::<Rejected>()) {
        1
    } else {
        2
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_rejection_is_exit_1_even_through_context() {
        let err: anyhow::Error = Rejected::err("2 errors");
        assert_eq!(code_for(&err), 1);

        let wrapped = err.context("while checking the manifest");
        assert_eq!(
            code_for(&wrapped),
            1,
            "adding context must not turn a rejection into a tool failure"
        );
    }

    /// The direction that does NOT work, pinned so nobody writes it by mistake.
    ///
    /// `err.context(Rejected)` attaches `Rejected` as anyhow's *context object*,
    /// which `chain()` does not yield — so the classification is invisible and
    /// the command silently exits 2 while reporting a wrong artefact. Build the
    /// `Rejected` as the outer error instead and fold the cause into its
    /// message.
    #[test]
    fn rejected_as_a_context_object_is_not_a_classification() {
        let err = anyhow::anyhow!("bad central directory").context(Rejected::new("did not verify"));
        assert_eq!(
            code_for(&err),
            2,
            "if this ever starts returning 1, anyhow changed and the note in main.rs's Verify arm \
             can be dropped"
        );
    }

    #[test]
    fn an_unclassified_error_is_exit_2() {
        let err = anyhow::anyhow!("No plugin.toml found");
        assert_eq!(code_for(&err), 2);
    }

    #[test]
    fn verdict_codes_match_the_documented_table() {
        assert_eq!(Verdict::Pass.code(), 0);
        assert_eq!(Verdict::Fail.code(), 1);
        assert_eq!(Verdict::of(true), Verdict::Pass);
        assert_eq!(Verdict::of(false), Verdict::Fail);
    }
}

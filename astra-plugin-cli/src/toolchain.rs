//! Finding the programs a build needs, and asking them their version.
//!
//! # Why this is not `Command::new(x).arg("--version").status().is_ok()`
//!
//! That is what this CLI did, and it is wrong in two ways that both produce a
//! *false yes*:
//!
//! * `status()` is `Ok` whenever the process **spawned**, whatever it then did.
//!   A program that exists, starts, and exits 1 because it does not understand
//!   `--version` — or because it is a broken installation — was reported as
//!   present.
//! * On Windows it misses `.cmd`/`.bat` shims. `npm`, `npx` and `bun` are
//!   installed there as `npm.cmd`; `CreateProcess` does not consult `PATHEXT`
//!   the way a shell does, so `Command::new("npm")` fails with "program not
//!   found" on a machine where `npm` works perfectly in every terminal. The
//!   effect was `astra-plugin build` deciding a TypeScript plugin had no
//!   bundler on exactly the platform most authors use.
//!
//! The `which` crate answers the real question — *does PATH resolve this name
//! to an executable file* — with the platform's own rules, and without running
//! anything.

use std::path::PathBuf;

/// Does PATH resolve `program` to something executable?
///
/// Runs nothing: presence is a filesystem question, and answering it by
//  spawning is how a program that exits non-zero got called missing.
pub fn exists(program: &str) -> bool {
    which::which(program).is_ok()
}

/// Where PATH resolves `program`, if anywhere.
pub fn locate(program: &str) -> Option<PathBuf> {
    which::which(program).ok()
}

/// `program --version`, first line, trimmed — `None` when the program is
/// absent, cannot be run, or exits non-zero.
///
/// The exit status is checked here precisely because [`exists`] does not run
/// anything: this is the one place where "it ran and it worked" is the question
/// being asked.
pub fn version(program: &str) -> Option<String> {
    let path = locate(program)?;
    let out = std::process::Command::new(path)
        .arg("--version")
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    let text = String::from_utf8_lossy(if out.stdout.is_empty() {
        &out.stderr
    } else {
        &out.stdout
    });
    let line = text.lines().next()?.trim().to_string();
    if line.is_empty() { None } else { Some(line) }
}

/// The first integer in a version string — `20` from `v20.11.1`, `3` from
/// `Python 3.12.4`.
pub fn major(version: &str) -> Option<u32> {
    let mut digits = String::new();
    let mut seen = false;
    for c in version.chars() {
        if c.is_ascii_digit() {
            digits.push(c);
            seen = true;
        } else if seen {
            break;
        }
    }
    digits.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_program_that_is_not_on_path_is_absent() {
        assert!(!exists("astra-plugin-no-such-program-9f3c"));
        assert!(locate("astra-plugin-no-such-program-9f3c").is_none());
        assert!(version("astra-plugin-no-such-program-9f3c").is_none());
    }

    /// The regression the `which` crate was adopted for.
    ///
    /// The old implementation was `Command::new(cmd).arg("--version").status()
    /// .is_ok()`, which is `Ok` for any program that *spawns*. `false` is the
    /// only right answer for a program that runs and then fails, and the only
    /// portable program guaranteed to do that is one that does not exist —
    /// which the case above covers. What this pins is the shape: presence is
    /// decided without spawning anything, so an exit status cannot enter into
    /// it. `cargo` is running this test, so it is on PATH by construction.
    #[test]
    fn presence_is_decided_without_running_the_program() {
        assert!(exists("cargo"), "cargo built this test, so it is on PATH");
        // And it resolves to a real file, which is what `which` guarantees and
        // a successful spawn does not.
        assert!(locate("cargo").is_some_and(|p| p.is_file()));
    }

    #[test]
    fn major_reads_the_first_integer() {
        assert_eq!(major("v20.11.1"), Some(20));
        assert_eq!(major("Python 3.12.4"), Some(3));
        assert_eq!(major("1.0.0-beta"), Some(1));
        assert_eq!(major("no digits here"), None);
    }
}

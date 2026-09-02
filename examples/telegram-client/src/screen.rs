//! Capturing the screen for `/screenshot`.
//!
//! Astra has this already — `MediaService` carries *"Capture a PNG screenshot
//! of the requested monitor (0 = primary)"* — and the plugin cannot call it:
//! `MediaService` is a daemon service, and a plugin's session token is refused
//! on every gRPC path outside `PluginHostService`. So the picture is taken here
//! instead, by a process that happens to be running as the user with no sandbox
//! around it. That is not a loophole, it is the documented state of things
//! (`docs/en/1-orientation/security.md`), and it is the reason the command is
//! off until it is switched on.
//!
//! # Why this is a Windows command
//!
//! [`SUPPORTED`] is `false` everywhere else, and `Cargo.toml` does not even
//! compile `xcap` in. The short version: on Linux `xcap` needs PipeWire and
//! libxcb, both as `-sys` crates, and a plugin that links them does not start
//! at all on a machine without those shared objects — turning a Telegram
//! bridge that needs no display into one that cannot load on a headless box,
//! for the sake of a command that ships switched off. The long version is the
//! comment over the dependency in `Cargo.toml`.
//!
//! This is a limit worth removing later, and removing it means capturing on
//! Linux without a `-sys` crate — X11's `GetImage` through a pure-Rust
//! connection — rather than adding the system packages.

use std::path::{Path, PathBuf};

use anyhow::Result;

/// Whether [`capture`] can actually take a picture on this build.
///
/// A `const` and not a `cfg!` at the call site, so the caller reads as one
/// branch on a fact rather than as conditional compilation spread through the
/// command handler.
pub const SUPPORTED: bool = cfg!(windows);

/// Capture the primary monitor to a PNG inside `dir`, and say which monitor it
/// was so the caller can put a name on the picture.
///
/// Blocking, and deliberately not `async`: this reads a framebuffer and encodes
/// a few megabytes of PNG. The caller hands it to `spawn_blocking` rather than
/// stalling the polling loop, which is also what stops Telegram's long poll
/// from timing out under it.
#[cfg(windows)]
pub fn capture(dir: &Path) -> Result<(PathBuf, String)> {
    use anyhow::Context;
    use xcap::Monitor;

    let monitors = Monitor::all().context("no monitors could be enumerated")?;

    // Primary if the platform names one, else whichever came first — a headless
    // box or an unusual compositor can answer "none of them", and a picture of
    // some screen beats an error saying there is no favourite.
    let monitor = monitors
        .iter()
        .find(|m| m.is_primary().unwrap_or(false))
        .or_else(|| monitors.first())
        .context("this machine reports no monitors at all")?;

    let name = monitor
        .name()
        .unwrap_or_else(|_| "unknown display".to_string());

    let image = monitor
        .capture_image()
        .with_context(|| format!("capturing {name}"))?;

    // Named for the moment it was taken, so two in a row never collide and a
    // leftover file says when it came from.
    let path = dir.join(format!(
        "astra-telegram-screenshot-{}.png",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0)
    ));
    image
        .save(&path)
        .with_context(|| format!("writing {}", path.display()))?;

    Ok((path, name))
}

/// The same door on a build with no capture behind it.
///
/// It exists so the rest of the plugin compiles unchanged and the command has
/// exactly one implementation to call; [`SUPPORTED`] is what the caller asks
/// first, so in practice this is never reached.
#[cfg(not(windows))]
pub fn capture(_dir: &Path) -> Result<(PathBuf, String)> {
    anyhow::bail!(
        "this build cannot capture a screen: the capture backend is compiled in on \
         Windows only, because on Linux it would link PipeWire and libxcb and the \
         plugin would then refuse to start on a machine without them"
    )
}

#[cfg(test)]
mod tests {
    /// The const and the dependency have to agree, or `/screenshot` either
    /// answers "unsupported" on a build that could have taken the picture, or
    /// calls into a backend that was never compiled.
    #[test]
    fn supported_says_what_cargo_toml_compiled() {
        assert_eq!(super::SUPPORTED, cfg!(windows));
        #[cfg(windows)]
        {
            // Names the crate, so removing it from `[target.'cfg(windows)']`
            // without touching this file stops the build here rather than in
            // the command handler.
            let _ = xcap::Monitor::all;
        }
    }
}

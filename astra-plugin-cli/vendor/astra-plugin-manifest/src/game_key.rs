//! **The one spelling grammar of a game's KEY** — the string Astra names a game by: a Steam appid
//! (`"620"`), a hand-added game (`local-<16 lowercase hex>`), an Epic Games Store game
//! (`epic-<name>`) or a GOG game (`gog-<product id>`).
//!
//! It lives here, in the crate every reader of `plugin.toml` shares, so that the daemon's typed
//! `GameKey` and the manifest's `[plugin] target` validation read a key through the SAME
//! function and cannot drift apart. This module is pure: no I/O, no allocation beyond the
//! returned value.

/// The prefix of a game added by hand.
pub const LOCAL_PREFIX: &str = "local-";
/// The length of a hand-added game's random part, in lowercase hex digits.
pub const LOCAL_HEX_LEN: usize = 16;
/// The prefix of an Epic Games Store game.
pub const EPIC_PREFIX: &str = "epic-";
/// The longest Epic `AppName` a key carries.
pub const EPIC_NAME_MAX: usize = 64;
/// The prefix of a GOG game.
pub const GOG_PREFIX: &str = "gog-";
/// The most digits a GOG product id has (`u64::MAX` is 20).
pub const GOG_DIGITS_MAX: usize = 20;

/// A character an Epic key's name may start with: a lowercase letter or a digit.
fn is_epic_head(b: u8) -> bool {
    b.is_ascii_lowercase() || b.is_ascii_digit()
}

/// What a key's spelling says it is. Carries the number where there is one, never the text.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GameKeySpelling {
    /// A Steam appid, decimal digits that fit a `u32` (zero included: the daemon's own
    /// reading accepts it; a manifest's `target` additionally refuses it).
    Steam(u32),
    /// `local-<16 lowercase hex>`.
    Local,
    /// `epic-<name>`, `[a-z0-9][a-z0-9_-]{0,63}`.
    Epic,
    /// `gog-<product id>`, a `u64` with no sign and no leading zero.
    Gog(u64),
}

impl GameKeySpelling {
    /// The spelling `raw` is, or `None` when it names no game: an empty string, a sign, a space,
    /// a separator, upper-case hex, a short or long random part.
    pub fn parse(raw: &str) -> Option<GameKeySpelling> {
        if let Some(hex) = raw.strip_prefix(LOCAL_PREFIX) {
            let ok = hex.len() == LOCAL_HEX_LEN
                && hex
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b));
            return ok.then_some(GameKeySpelling::Local);
        }
        if let Some(name) = raw.strip_prefix(EPIC_PREFIX) {
            let mut bytes = name.bytes();
            let ok = (1..=EPIC_NAME_MAX).contains(&name.len())
                && bytes.next().is_some_and(is_epic_head)
                && bytes.all(|b| is_epic_head(b) || b == b'_' || b == b'-');
            return ok.then_some(GameKeySpelling::Epic);
        }
        if let Some(id) = raw.strip_prefix(GOG_PREFIX) {
            // One spelling per number: no sign, no leading zero (`gog-007` is not `gog-7`).
            let ok = (1..=GOG_DIGITS_MAX).contains(&id.len())
                && id.bytes().all(|b| b.is_ascii_digit())
                && !id.starts_with('0');
            return ok
                .then(|| id.parse::<u64>().ok().map(GameKeySpelling::Gog))
                .flatten();
        }
        // Digits only: `u32::from_str` also takes a leading `+`.
        if raw.is_empty() || !raw.bytes().all(|b| b.is_ascii_digit()) {
            return None;
        }
        raw.parse::<u32>().ok().map(GameKeySpelling::Steam)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_store_spelling_is_read() {
        assert_eq!(
            GameKeySpelling::parse("620"),
            Some(GameKeySpelling::Steam(620))
        );
        assert_eq!(GameKeySpelling::parse("0"), Some(GameKeySpelling::Steam(0)));
        assert_eq!(
            GameKeySpelling::parse("local-0123456789abcdef"),
            Some(GameKeySpelling::Local)
        );
        assert_eq!(
            GameKeySpelling::parse("epic-a_b-1"),
            Some(GameKeySpelling::Epic)
        );
        assert_eq!(
            GameKeySpelling::parse("gog-7"),
            Some(GameKeySpelling::Gog(7))
        );
        for bad in [
            "",
            "+1",
            "gog-07",
            "epic-A",
            "local-ABCDEF0123456789",
            "4294967296",
        ] {
            assert_eq!(GameKeySpelling::parse(bad), None, "{bad:?}");
        }
    }
}

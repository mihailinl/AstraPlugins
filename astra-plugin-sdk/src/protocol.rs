//! The plugin wire-protocol handshake.
//!
//! Before this existed there was no version anywhere in either direction, so an
//! old plugin meeting a new daemon (or the reverse) failed at the first RPC one
//! side did not have — with an error that named neither the cause nor the fix.
//! Registration now carries an integer both ways, and the mismatch is decided
//! once, at the handshake, in [`evaluate`].

use crate::proto;

/// The wire-protocol generation this SDK speaks.
///
/// One integer, in four places that must agree: here, `proto/PROTO_VERSION`
/// (`protocol=`), the `// protocol: N` header of the generated `plugin.proto`,
/// and the daemon's `PLUGIN_PROTOCOL_VERSION`. The Python and TypeScript SDKs
/// carry the same constant under the same name.
pub const PROTOCOL_VERSION: u32 = 1;

/// The oldest daemon protocol this SDK will serve.
///
/// The mirror image of the daemon's own floor. A daemon below this would have
/// the SDK calling host RPCs it does not implement, so the plugin says so once
/// and exits instead of running half-broken.
///
/// **`0` is allowed on purpose, and that is not the same as having no floor.**
/// Protocol 1 *is* the pre-handshake plugin surface: Astra v0.1.0 — the only
/// released Astra — has a byte-identical `PluginHostService`, already carries
/// every plugin-facing field this SDK sends, and already issues a per-plugin
/// session token to *every* plugin (`host_service.rs`, `SECURITY(B1)`). It
/// simply predates the `protocol_version` field, and proto3 delivers an absent
/// field as `0`. A floor of 1 would therefore refuse the one daemon that can
/// serve this SDK perfectly, on the grounds that it never learned to say so.
///
/// The capability this SDK genuinely needs is checked directly rather than
/// inferred from an integer: `host_client.rs` fails closed on an empty
/// `client_session_token` right after `evaluate`, because that — not a version
/// number — is what decides whether any host RPC can succeed.
///
/// Raise this to 2 in the release where the SDK starts calling something
/// protocol 1 does not have. The `< floor` branch below and its sentence stay
/// live for exactly that day; [`evaluate_against`] lets a test rehearse it now.
pub const MIN_SUPPORTED_DAEMON_PROTOCOL: u32 = 0;

/// Reported to the daemon for support triage only; never gates anything.
pub const SDK_NAME: &str = "astra-plugin-sdk-rust";

/// This crate's own release, alongside [`SDK_NAME`].
pub const SDK_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Exit code for a protocol mismatch: `EX_CONFIG` from `sysexits.h`.
///
/// Deliberately not 1. The daemon logs a plugin's exit code, and "the
/// configuration of this machine is wrong" is exactly the right category —
/// nothing about retrying, restarting or the plugin's own logic will change the
/// outcome until somebody installs a different build.
pub const EXIT_PROTOCOL_INCOMPATIBLE: i32 = 78;

/// A handshake that cannot proceed. `Display` is the one sentence the plugin
/// prints before exiting [`EXIT_PROTOCOL_INCOMPATIBLE`].
#[derive(Debug, Clone)]
pub struct ProtocolMismatch(String);

impl std::fmt::Display for ProtocolMismatch {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for ProtocolMismatch {}

/// Decide whether this SDK can serve the daemon that just answered `Register`.
///
/// Pure, so the rule is testable without a daemon and a socket. Two ways it can
/// fail, and they are not the same failure:
///
/// - **The daemon refused us** for being too old. It told us its floor, so the
///   sentence can name the number this plugin has to reach.
/// - **The daemon is older than this SDK's floor.** Nothing refused anything —
///   it is the SDK that would start calling RPCs the daemon lacks. Stop before
///   doing that.
///
/// Anything else (a refusal for a bad auth token, an unknown plugin id) is not
/// a protocol matter and is left to the caller's ordinary error path.
pub fn evaluate(resp: &proto::PluginRegisterResponse) -> Result<(), ProtocolMismatch> {
    evaluate_against(resp, MIN_SUPPORTED_DAEMON_PROTOCOL)
}

/// [`evaluate`] with the floor passed in, so a test can ask the real question —
/// "what does an SDK whose floor is 2 see from a daemon that reports 0?" —
/// without waiting for the release that raises the shipped floor. The mirror of
/// the daemon's own `check_protocol_against`.
fn evaluate_against(
    resp: &proto::PluginRegisterResponse,
    floor: u32,
) -> Result<(), ProtocolMismatch> {
    if let Some(detail) = &resp.error_detail
        && detail.code == proto::PluginErrorCode::PluginErrorProtocolTooOld as i32
    {
        // The daemon's own words first — it knows its floor, and it is the side
        // that decided. The hint is what the author acts on.
        let mut sentence = if detail.message.is_empty() {
            format!(
                "This plugin speaks Astra plugin protocol {PROTOCOL_VERSION}, which this Astra \
                 no longer accepts (it needs {} or newer).",
                resp.min_supported_protocol
            )
        } else {
            detail.message.clone()
        };
        if !detail.hint.is_empty() {
            sentence.push(' ');
            sentence.push_str(&detail.hint);
        }
        return Err(ProtocolMismatch(sentence));
    }

    if resp.protocol_version < floor {
        let reported = if resp.protocol_version == 0 {
            "did not report a protocol version at all".to_string()
        } else {
            format!("speaks protocol {}", resp.protocol_version)
        };
        return Err(ProtocolMismatch(format!(
            "This Astra {reported}, and this plugin needs protocol {floor} or newer — update \
             Astra, or install a build of this plugin made for the Astra you have."
        )));
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn response(protocol_version: u32, min_supported: u32) -> proto::PluginRegisterResponse {
        proto::PluginRegisterResponse {
            success: true,
            client_session_token: "tok".into(),
            protocol_version,
            min_supported_protocol: min_supported,
            ..Default::default()
        }
    }

    /// THE acceptance case for 1.3: an SDK built at protocol 1 meets a daemon
    /// whose floor is 2. It gets one sentence and stops — it does not go on to
    /// call RPCs that daemon would answer `UNIMPLEMENTED`.
    #[test]
    fn a_daemon_whose_floor_is_two_stops_an_sdk_at_one() {
        assert_eq!(PROTOCOL_VERSION, 1, "this test is written for protocol 1");

        let mut resp = response(2, 2);
        resp.success = false;
        resp.error = "too old".into();
        resp.error_detail = Some(proto::PluginError {
            code: proto::PluginErrorCode::PluginErrorProtocolTooOld as i32,
            message: "Plugin 'dice-roller' speaks protocol 1; this daemon speaks 2 and accepts \
                      2 or newer."
                .into(),
            hint: "Rebuild the plugin against an Astra plugin SDK whose PROTOCOL_VERSION is at \
                   least 2, then reinstall it."
                .into(),
            ..Default::default()
        });

        let sentence = evaluate(&resp).expect_err("floor 2 must refuse an SDK at 1").to_string();
        assert!(sentence.contains('2'), "{sentence}");
        assert!(
            sentence.contains("PROTOCOL_VERSION"),
            "the fix has to be in the sentence, not just the cause: {sentence}"
        );
    }

    /// A daemon that predates the handshake reports nothing, and is SERVED.
    ///
    /// This is Astra v0.1.0, the released build: identical `PluginHostService`,
    /// every field this SDK sends already present, a session token issued to
    /// every plugin. The only thing it cannot do is name its own generation.
    /// Refusing it would have made every plugin built with this SDK dead on the
    /// only Astra in the world.
    #[test]
    fn a_daemon_that_reports_no_protocol_is_served() {
        assert_eq!(
            MIN_SUPPORTED_DAEMON_PROTOCOL, 0,
            "protocol 1 IS the pre-handshake surface; a floor of 1 refuses Astra v0.1.0"
        );
        assert!(evaluate(&response(0, 0)).is_ok());
    }

    /// …and the refusal branch is still live, for the release that needs it. A
    /// floor of 2 stops a daemon that reports nothing, in the daemon's absence
    /// of words — same shape as the daemon's own `check_protocol_against`.
    #[test]
    fn a_floor_of_two_refuses_a_daemon_that_reports_no_protocol() {
        let sentence = evaluate_against(&response(0, 0), 2)
            .expect_err("protocol 0 is below a floor of 2")
            .to_string();
        assert!(sentence.contains("did not report"), "{sentence}");
        assert!(sentence.contains('2'), "{sentence}");
        assert!(sentence.contains("update Astra"), "{sentence}");

        // A daemon that DOES report, but below the floor, is named by number.
        let sentence = evaluate_against(&response(1, 1), 2)
            .expect_err("protocol 1 is below a floor of 2")
            .to_string();
        assert!(sentence.contains("speaks protocol 1"), "{sentence}");
    }

    /// A daemon NEWER than this SDK is fine: it simply never calls the hooks
    /// this plugin does not have, and `UNIMPLEMENTED` means "absent".
    #[test]
    fn a_newer_daemon_is_served() {
        assert!(evaluate(&response(PROTOCOL_VERSION + 5, PROTOCOL_VERSION)).is_ok());
        assert!(evaluate(&response(PROTOCOL_VERSION, PROTOCOL_VERSION)).is_ok());
    }

    /// A refusal that is NOT about the protocol stays with the ordinary error
    /// path — exiting 78 ("this machine is misconfigured") over a bad auth
    /// token would send the author to fix the wrong thing.
    #[test]
    fn a_non_protocol_refusal_is_not_a_protocol_mismatch() {
        let mut resp = response(PROTOCOL_VERSION, PROTOCOL_VERSION);
        resp.success = false;
        resp.error = "Invalid auth token".into();
        resp.error_detail = Some(proto::PluginError {
            code: proto::PluginErrorCode::PluginErrorAuth as i32,
            message: "Invalid auth token".into(),
            hint: "Let the daemon spawn the plugin.".into(),
            ..Default::default()
        });
        assert!(evaluate(&resp).is_ok());
    }
}

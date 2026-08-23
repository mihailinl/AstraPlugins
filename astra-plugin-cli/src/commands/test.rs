//! `astra-plugin test` — run the conformance suite against a real plugin
//! process.
//!
//! # What this is
//!
//! The SDK's level-2 harness, pointed at a **process** instead of at a type.
//! [`astra_plugin_sdk::testing::WireHarness`] starts a Rust plugin in the test
//! binary's own address space; this starts *the executable the daemon would
//! start*, in any language, with the argv the daemon passes, and drives it with
//! a `PluginCapabilityServiceClient` carrying the token the daemon presents.
//!
//! The daemon half is not re-implemented here. It is
//! [`astra_plugin_sdk::testing::MockDaemon`] — the same `PluginHostService`,
//! the same "only `Register` is auth-exempt" rule, the same per-rpc permission
//! gate, the same protocol handshake. A second mock daemon in this crate would
//! be a second opinion about the protocol, and this repo already paid for
//! having several of those.
//!
//! # What it asserts
//!
//! The hook list is `spec/generated/conformance.json`, generated from
//! `spec/hooks.yaml`, vendored next to this file and drift-checked by
//! [`tests::the_vendored_conformance_list_matches_the_spec`]. For every hook
//! whose `capability` this plugin's manifest declares:
//!
//! * `requirement: required` **must not** answer `UNIMPLEMENTED`.
//! * `requirement: optional` **may**. That exemption is not laxity, it is the
//!   forward-compatibility contract: Phase 1 fixed `Unimplemented` to mean *the
//!   hook is absent*, so an optional hook a plugin does not serve is a plugin
//!   the daemon carries on without. Without the exemption a scaffold that
//!   declared every capability would be indistinguishable from a broken plugin,
//!   and the check would be one everybody learns to ignore.
//!
//! Plus the things the hook list cannot express:
//!
//! * every tool's `parameters_json` parses, and its root is `"type": "object"`
//!   — a schema whose root is a string or an array is one the model cannot
//!   produce arguments for, and the daemon forwards it to the provider as-is;
//! * `[config].schema` parses, has an object root, and **round-trips**: an
//!   instance built from its defaults is handed back through `OnConfigChanged`
//!   and the plugin must still answer `HealthCheck` afterwards;
//! * `HealthCheck` answers at all;
//! * `Shutdown` is honoured **within the grace in `spec/limits.yaml`**
//!   (`plugin_stop_grace_secs`), because past that the daemon kills the process
//!   group and the plugin's tidy path never runs.
//!
//! …and the two halves of "is this plugin actually talking to the daemon", which
//! nothing here used to look at. Every check above drives the plugin *inbound*
//! and reads the answer, so the whole plugin→daemon direction was invisible: a
//! host client that stopped sending `x-session-token` produced an
//! `UNAUTHENTICATED` for every `fire_trigger`, `log`, `get_config`,
//! `set_variable` and `push_to_ui` the plugin made, and this command still
//! printed `OK`. That is the Phase 0 state that made the protocol unusable in
//! all three languages.
//!
//! * **the plugin said something before the daemon gave up.** The daemon's
//!   readiness signal is the child's first line on stdout *or* stderr, within
//!   `plugin_start_timeout_secs`; past that it kills the process group and
//!   classifies the failure `start_timeout`. Checked before the probes, because
//!   a block-buffered stream flushes on exit and a check made after `Shutdown`
//!   would see a line the daemon never saw.
//! * **the plugin talked to the daemon, and every call carried the token.**
//!   Read off [`MockDaemon`]'s own record, which counts both the calls that
//!   arrived and the ones it refused.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::OnceLock;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use astra_plugin_sdk::limits::{PLUGIN_START_TIMEOUT_SECS, PLUGIN_STOP_GRACE_SECS};
use astra_plugin_sdk::proto;
use astra_plugin_sdk::proto::plugin_capability_service_client::PluginCapabilityServiceClient;
use astra_plugin_sdk::testing::MockDaemon;
use serde_json::{Value, json};
use tokio::process::{Child, Command};

use crate::hprintln;
use crate::output::{Rejected, Verdict};

/// The hook list, vendored from `spec/generated/conformance.json`.
///
/// Vendored rather than read from disk because `astra-plugin test` runs in an
/// author's project, where this repo's `spec/` does not exist. The unit test
/// below fails if the copy drifts.
const CONFORMANCE_JSON: &str = include_str!("../conformance.json");

/// Capability every plugin has, whatever its manifest says.
const CORE: &str = "core";

/// The hooks whose answers later hooks need as arguments, probed first.
///
/// `CallTool` needs a tool name, `ExecuteAction` an action type,
/// `OnActiveTriggers` a trigger type, `TtsSynthesize` a voice id. Each is
/// probed exactly once and its answer kept.
const DISCOVERY: &[&str] = &[
    "ListTools",
    "GetPluginActionTypes",
    "GetPluginTriggerTypes",
    "TtsListVoices",
];

/// How long one probe may take before it is called a hang.
///
/// Deliberately well under [`PLUGIN_START_TIMEOUT_SECS`]: a hook that takes
/// this long has failed even if it would eventually answer, because the daemon
/// applies `entry.call_timeout_secs` to the same call.
const PROBE_TIMEOUT: Duration = Duration::from_secs(10);

pub struct TestOptions<'a> {
    pub path: &'a str,
    /// Skip the language build step and use whatever is already on disk.
    pub no_build: bool,
    /// Write the machine-readable conformance report here. This is the file
    /// `tools/parity/check.py --rules R7 --report <file>` reads.
    pub report: Option<&'a str>,
}

/// One unary call, bounded by [`PROBE_TIMEOUT`], with a timed-out call
/// reported as a `tonic::Status` so every arm below has one error type.
///
/// A macro and not a function: the borrow of the client lives exactly as long
/// as the call, and the generic-closure spelling of that (`for<'a> FnOnce(&'a
/// mut C) -> impl Future + 'a`) is not expressible on stable Rust without
/// boxing every future on the probe path.
macro_rules! probe_call {
    ($client:expr, $rpc:expr, $method:ident($($arg:tt)*)) => {{
        match tokio::time::timeout(PROBE_TIMEOUT, $client.$method(req($($arg)*))).await {
            Ok(r) => r.map(tonic::Response::into_inner),
            Err(_) => Err(tonic::Status::deadline_exceeded(format!(
                "{} did not answer within {:?}",
                $rpc, PROBE_TIMEOUT
            ))),
        }
    }};
}

// ── one hook's row in the conformance list ───────────────────────────────────

struct Hook {
    rpc: String,
    capability: String,
    required: bool,
    /// `unary` | `server` | `client` | `bidi`. Read by
    /// `the_streaming_probes_are_the_streaming_hooks`, which is where it earns
    /// its place: the engine's own list of which hooks it streams has to match
    /// the spec's.
    #[cfg_attr(not(test), allow(dead_code))]
    streaming: String,
    teardown: bool,
}

fn conformance_hooks() -> Result<Vec<Hook>> {
    let doc: Value =
        serde_json::from_str(CONFORMANCE_JSON).context("the vendored conformance list is not JSON")?;
    let rows = doc
        .get("hooks")
        .and_then(Value::as_array)
        .context("the vendored conformance list has no `hooks` array")?;
    rows.iter()
        .map(|h| {
            let get = |k: &str| -> Result<String> {
                h.get(k)
                    .and_then(Value::as_str)
                    .map(str::to_string)
                    .with_context(|| format!("conformance row is missing `{k}`: {h}"))
            };
            let requirement = get("requirement")?;
            Ok(Hook {
                rpc: get("rpc")?,
                capability: get("capability")?,
                required: requirement == "required",
                streaming: get("streaming")?,
                teardown: get("phase")? == "teardown",
            })
        })
        .collect()
}

// ── what one probe concluded ─────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Status {
    /// The plugin answered.
    Ok,
    /// The plugin answered `UNIMPLEMENTED` — protocol for "this hook is absent".
    Unimplemented,
    /// The rpc failed for any other reason, or did not come back in time.
    Error,
    /// Not exercised: the manifest does not declare this hook's capability.
    Skipped,
}

impl Status {
    fn as_str(self) -> &'static str {
        match self {
            Status::Ok => "ok",
            Status::Unimplemented => "unimplemented",
            Status::Error => "error",
            Status::Skipped => "skipped",
        }
    }
}

struct Probe {
    rpc: String,
    capability: String,
    required: bool,
    status: Status,
    detail: String,
}

/// Everything the run concluded, in the shape `--json` and `--report` print.
struct Findings {
    plugin_id: String,
    language: String,
    capabilities: Vec<String>,
    probes: Vec<Probe>,
    /// Assertions that are not one hook: schemas, the shutdown grace.
    checks: Vec<(String, bool, String)>,
}

impl Findings {
    fn failures(&self) -> Vec<String> {
        let mut out: Vec<String> = self
            .probes
            .iter()
            .filter(|p| p.required && matches!(p.status, Status::Unimplemented | Status::Error))
            .map(|p| match p.status {
                Status::Unimplemented => format!(
                    "{}: answered UNIMPLEMENTED. spec/hooks.yaml marks it `requirement: required` \
                     for the `{}` capability, which this plugin declares — the daemon will call \
                     it and get nothing.",
                    p.rpc, p.capability
                ),
                _ => format!("{}: {}", p.rpc, p.detail),
            })
            .collect();
        out.extend(
            self.checks
                .iter()
                .filter(|(_, ok, _)| !ok)
                .map(|(name, _, detail)| format!("{name}: {detail}")),
        );
        out
    }

    fn to_json(&self) -> Value {
        json!({
            "plugin_id": self.plugin_id,
            "language": self.language,
            "capabilities": self.capabilities,
            "protocol": serde_json::from_str::<Value>(CONFORMANCE_JSON)
                .ok()
                .and_then(|d| d.get("protocol").cloned())
                .unwrap_or(Value::Null),
            "hooks": self.probes.iter().map(|p| json!({
                "rpc": p.rpc,
                "capability": p.capability,
                "requirement": if p.required { "required" } else { "optional" },
                "status": p.status.as_str(),
                "detail": p.detail,
            })).collect::<Vec<_>>(),
            "checks": self.checks.iter().map(|(name, ok, detail)| json!({
                "name": name, "ok": ok, "detail": detail,
            })).collect::<Vec<_>>(),
            "failures": self.failures(),
        })
    }
}

// ── the run ──────────────────────────────────────────────────────────────────

pub async fn run(opts: TestOptions<'_>) -> Result<Verdict> {
    let dir = Path::new(opts.path)
        .canonicalize()
        .context("Invalid plugin path")?;
    let manifest_path = dir.join("plugin.toml");
    if !manifest_path.exists() {
        anyhow::bail!("No plugin.toml found at {}", manifest_path.display());
    }
    let manifest_str = std::fs::read_to_string(&manifest_path)?;
    let manifest: astra_plugin_manifest::PluginManifest =
        toml::from_str(&manifest_str).context("Failed to parse plugin.toml")?;

    let plugin_id = manifest.plugin.id.clone();
    let capabilities = manifest.capabilities.as_list();
    let language = crate::commands::build::detect_language(&dir);

    hprintln!("Testing plugin '{plugin_id}' ({language}) at {}", dir.display());
    hprintln!(
        "  Capabilities: {}",
        if capabilities.is_empty() {
            "none".to_string()
        } else {
            capabilities.join(", ")
        }
    );

    if !opts.no_build {
        crate::commands::build::build_project(&dir)?;
    }

    // The config the daemon will hand this plugin at registration. Built from
    // `[config].schema`'s own defaults, so the round-trip is against the
    // author's declared shape rather than an empty object that no schema would
    // reject.
    let config_schema: Option<Value> = manifest
        .config
        .as_ref()
        .filter(|c| !c.schema.trim().is_empty())
        .map(|c| serde_json::from_str(&c.schema))
        .transpose()
        .context("[config].schema is not valid JSON")?;
    let config_instance = config_schema
        .as_ref()
        .map(defaults_from_schema)
        .unwrap_or_else(|| json!({}));

    let daemon = MockDaemon::start()
        .await
        .context("could not start the mock daemon")?;
    daemon.set_config_json(config_instance.to_string());
    let _ = SPAWN_TOKEN.set(daemon.spawn_token());

    let (mut child, first_output) =
        spawn_plugin(&dir, &manifest, daemon.addr(), daemon.spawn_token(), &capabilities)
            .context("could not start the plugin process")?;

    let outcome = drive(
        &daemon,
        &mut child,
        first_output,
        &dir,
        &plugin_id,
        &language,
        &capabilities,
        config_schema.as_ref(),
        &config_instance,
    )
    .await;

    // Whatever happened, do not leave a process behind.
    let _ = child.start_kill();
    let _ = child.wait().await;

    let findings = outcome?;
    let failures = findings.failures();
    let verdict = Verdict::of(failures.is_empty());

    if let Some(path) = opts.report {
        std::fs::write(path, serde_json::to_string_pretty(&findings.to_json())?)
            .with_context(|| format!("could not write the conformance report to {path}"))?;
        hprintln!("  Report: {path}");
    }

    report_human(&findings, &failures);
    crate::output::emit("test", &verdict, findings.to_json());

    if verdict == Verdict::Fail && !crate::output::json_mode() {
        return Err(Rejected::err(format!(
            "conformance failed: {} problem(s)",
            failures.len()
        )));
    }
    Ok(verdict)
}

fn report_human(findings: &Findings, failures: &[String]) {
    hprintln!();
    for p in &findings.probes {
        let mark = match p.status {
            Status::Ok => "ok  ",
            Status::Unimplemented if p.required => "FAIL",
            Status::Unimplemented => "----",
            Status::Error if p.required => "FAIL",
            Status::Error => "warn",
            Status::Skipped => "skip",
        };
        if p.status == Status::Skipped {
            continue;
        }
        hprintln!(
            "  [{mark}] {:<24} {:<9} {}",
            p.rpc,
            if p.required { "required" } else { "optional" },
            p.detail
        );
    }
    for (name, ok, detail) in &findings.checks {
        hprintln!("  [{}] {name}: {detail}", if *ok { "ok  " } else { "FAIL" });
    }
    hprintln!();
    if failures.is_empty() {
        let exercised = findings
            .probes
            .iter()
            .filter(|p| p.status != Status::Skipped)
            .count();
        hprintln!(
            "  OK: {exercised} hook(s) exercised, {} check(s) passed.",
            findings.checks.len()
        );
    } else {
        for f in failures {
            hprintln!("  FAIL: {f}");
        }
    }
}

/// The whole conversation with a plugin that is already running.
#[allow(clippy::too_many_arguments)]
async fn drive(
    daemon: &MockDaemon,
    child: &mut Child,
    mut first_output: FirstOutput,
    dir: &Path,
    plugin_id: &str,
    language: &str,
    capabilities: &[String],
    config_schema: Option<&Value>,
    config_instance: &Value,
) -> Result<Findings> {
    let declared: BTreeSet<&str> = capabilities.iter().map(String::as_str).collect();

    let port = await_registration(daemon, child).await?;
    // Before anything else, and before `Shutdown` above all: the readiness
    // signal is only meaningful while the process is still running. A plugin
    // whose stdout is block-buffered flushes the whole buffer when the
    // interpreter exits, so a check made after teardown sees a first line that
    // the daemon — which had already killed the process at the start timeout —
    // never saw.
    let first_line = first_line_check(&mut first_output).await;
    let registration = daemon.registration().expect("registration was just observed");
    hprintln!(
        "  Registered: port {port}, protocol {}, sdk {} {}",
        registration.protocol_version,
        registration.sdk_name,
        registration.sdk_version
    );

    let mut client = connect(port).await?;
    let mut findings = Findings {
        plugin_id: plugin_id.to_string(),
        language: language.to_string(),
        capabilities: capabilities.to_vec(),
        probes: Vec::new(),
        checks: vec![first_line],
    };

    // State the probes feed each other: `CallTool` needs a tool name,
    // `ExecuteAction` an action type, `OnActiveTriggers` a trigger type.
    let mut tools: Vec<proto::PluginToolDef> = Vec::new();
    let mut actions: Vec<String> = Vec::new();
    let mut triggers: Vec<String> = Vec::new();
    let mut voices: Vec<String> = Vec::new();

    let hooks = conformance_hooks()?;
    let (mut probe_phase, teardown): (Vec<&Hook>, Vec<&Hook>) =
        hooks.iter().partition(|h| !h.teardown);

    // Discovery before use. `spec/hooks.yaml` is ordered for a reader, so
    // `ExecuteAction` comes before `GetPluginActionTypes`; calling them in that
    // order means executing an action whose type has not been asked for yet,
    // and reporting a healthy plugin as broken. The spec is the authority on
    // *which* hooks to call, never on the order — that is a property of the
    // hooks' arguments, and it lives here.
    probe_phase.sort_by_key(|h| !DISCOVERY.contains(&h.rpc.as_str()));

    for hook in probe_phase {
        if hook.capability != CORE && !declared.contains(hook.capability.as_str()) {
            findings.probes.push(Probe {
                rpc: hook.rpc.clone(),
                capability: hook.capability.clone(),
                required: hook.required,
                status: Status::Skipped,
                detail: format!("`{}` is not declared in plugin.toml", hook.capability),
            });
            continue;
        }

        // The four discovery hooks are probed and harvested in ONE call. Two
        // calls would be two chances for the plugin to answer differently, and
        // a `CallTool` against a tool that was in the first answer and not the
        // second is a confusing way to report a race.
        let (status, detail) = match hook.rpc.as_str() {
            "ListTools" => {
                let r = probe_call!(client, "ListTools", list_tools(proto::Empty {}));
                if let Ok(resp) = &r {
                    tools = resp.tools.clone();
                }
                classify(r.map(|resp| format!("{} tool(s)", resp.tools.len())))
            }
            "GetPluginActionTypes" => {
                let r = probe_call!(
                    client,
                    "GetPluginActionTypes",
                    get_plugin_action_types(proto::Empty {})
                );
                if let Ok(resp) = &r {
                    actions = resp.types.iter().map(|t| t.r#type.clone()).collect();
                }
                classify(r.map(|resp| format!("{} action type(s)", resp.types.len())))
            }
            "GetPluginTriggerTypes" => {
                let r = probe_call!(
                    client,
                    "GetPluginTriggerTypes",
                    get_plugin_trigger_types(proto::Empty {})
                );
                if let Ok(resp) = &r {
                    triggers = resp.types.iter().map(|t| t.r#type.clone()).collect();
                }
                classify(r.map(|resp| format!("{} trigger type(s)", resp.types.len())))
            }
            "TtsListVoices" => {
                let r = probe_call!(client, "TtsListVoices", tts_list_voices(proto::Empty {}));
                if let Ok(resp) = &r {
                    voices = resp.voices.iter().map(|v| v.id.clone()).collect();
                }
                classify(r.map(|resp| format!("{} voice(s)", resp.voices.len())))
            }
            _ => {
                probe_one(
                    &mut client,
                    hook,
                    config_instance,
                    &tools,
                    &actions,
                    &triggers,
                    &voices,
                )
                .await
            }
        };

        tracing::debug!(rpc = %hook.rpc, status = status.as_str(), %detail, "probe");
        findings.probes.push(Probe {
            rpc: hook.rpc.clone(),
            capability: hook.capability.clone(),
            required: hook.required,
            status,
            detail,
        });
    }

    // ── the assertions the hook list cannot express ──

    if declared.contains("tools") {
        findings.checks.push(tool_schemas_check(&tools));
    }
    findings
        .checks
        .push(config_schema_check(config_schema, config_instance));
    if config_schema.is_some() {
        // The round trip: the plugin was handed this config at registration and
        // is handed it again here. Answering `HealthCheck` afterwards is what
        // makes "it parsed it" observable from outside the process.
        let sent = probe_call!(client, "OnConfigChanged", on_config_changed(proto::PluginConfigChangedMsg {
                config_json: config_instance.to_string(),
            }));
        let healthy = probe_call!(client, "HealthCheck", health_check(proto::Empty {}));
        findings.checks.push(match (sent, healthy) {
            (Ok(_), Ok(h)) if h.healthy => (
                "config schema round-trips".into(),
                true,
                "the defaults from [config].schema were accepted and the plugin stayed healthy"
                    .into(),
            ),
            (Err(s), _) => (
                "config schema round-trips".into(),
                false,
                format!("OnConfigChanged rejected the schema's own defaults: {s}"),
            ),
            (_, Err(s)) => (
                "config schema round-trips".into(),
                false,
                format!("the plugin stopped answering HealthCheck after OnConfigChanged: {s}"),
            ),
            (_, Ok(h)) => (
                "config schema round-trips".into(),
                false,
                format!("the plugin reported itself unhealthy after OnConfigChanged: {}", h.status),
            ),
        });
    }

    // ── locale-round-trip ──
    findings
        .checks
        .extend(locale_round_trip(&mut client, dir, &declared).await);

    // The daemon set `ASTRA_PLUGIN_CAPABILITY_AUTH=require` on this spawn, so a
    // capability call carrying no `x-plugin-token` must be refused. This is the
    // one check here that tests something the plugin does *not* do, and it is
    // worth a row of its own: the plugin's gRPC server is loopback TCP on an
    // OS-assigned port, reachable by every process running as this user, and
    // without the check they can call `CallTool`, `OnConfigChanged` — which
    // repoints an API base URL, after which the plugin posts its real
    // credentials wherever it was told — or `Shutdown`.
    //
    // It runs before teardown, on `HealthCheck`, because that is the one RPC
    // every plugin must serve regardless of what it declares.
    let unauthenticated = tokio::time::timeout(
        PROBE_TIMEOUT,
        client.health_check(tonic::Request::new(proto::Empty {})),
    )
    .await;
    findings.checks.push(match unauthenticated {
        Err(_) => (
            "a call without the daemon's token is refused".into(),
            false,
            format!(
                "an unauthenticated HealthCheck was neither answered nor refused within \
                 {PROBE_TIMEOUT:?}"
            ),
        ),
        Ok(Err(s)) if s.code() == tonic::Code::Unauthenticated => (
            "a call without the daemon's token is refused".into(),
            true,
            "HealthCheck without `x-plugin-token` answered UNAUTHENTICATED".into(),
        ),
        Ok(Err(s)) => (
            "a call without the daemon's token is refused".into(),
            false,
            format!(
                "HealthCheck without `x-plugin-token` was refused with {} rather than \
                 UNAUTHENTICATED — the call did not get through, but the reason says the \
                 token guard is not what stopped it",
                s.code()
            ),
        ),
        Ok(Ok(_)) => (
            "a call without the daemon's token is refused".into(),
            false,
            "HealthCheck was ANSWERED without `x-plugin-token`. The daemon sets \
             ASTRA_PLUGIN_CAPABILITY_AUTH=require on every spawn, so any process running \
             as this user can reach this plugin's tools, config and shutdown. If you build \
             the server yourself rather than through the SDK's runner, guard it — see \
             docs/en/1-orientation/architecture.md."
                .into(),
        ),
    });

    // ── teardown ──
    for hook in teardown {
        let started = Instant::now();
        let sent = probe_call!(client, &hook.rpc, shutdown(proto::Empty {}));
        // The ACKNOWLEDGEMENT, measured here — before the wait for the process
        // to actually go. These used to be one number taken after both, and the
        // report then said "acknowledged in 5.0s" about a plugin that answered
        // in 120 ms and then hung: the same sentence for a slow handler and for
        // a wedged process, which need opposite fixes. It cost a real
        // investigation, reading a hung process as a slow one.
        let acknowledged = started.elapsed();
        // A SECOND clock, started after the acknowledgement, and it is
        // deliberate: `shutdown_check` takes "how long the RPC took" and "how
        // long we then waited", which are measured from two different origins.
        // The bug this replaces was one `elapsed` used for both, so the shape of
        // it — one number standing in for two — is not expressible here any
        // more.
        let waiting = Instant::now();
        let grace = Duration::from_secs(PLUGIN_STOP_GRACE_SECS);
        let exited = tokio::time::timeout(grace, child.wait()).await;
        let waited = waiting.elapsed();

        let (status, detail) = shutdown_probe(&sent, acknowledged);
        findings.probes.push(Probe {
            rpc: hook.rpc.clone(),
            capability: hook.capability.clone(),
            required: hook.required,
            status,
            detail,
        });
        findings.checks.push(shutdown_check(exited.is_ok(), acknowledged, waited));
    }

    // ── what the plugin said back, and whether the daemon could hear it ──
    findings.checks.extend(host_side_checks(daemon));

    Ok(findings)
}

/// Did the plugin produce a line of output inside the daemon's start window?
///
/// This is the readiness signal, not a nicety. `PendingSpawn::run` returns once
/// the OS reports the child alive **and the first line of output has been
/// observed**, and gives it `PLUGIN_START_TIMEOUT` (20 s) to do so; past that
/// the process group is killed and the failure is classified `start_timeout`
/// (`astra-daemon/src/plugins/instance.rs`). `Register` is a *later* event, so
/// waiting on registration — which is all this command used to do — cannot see
/// this at all.
///
/// The classic way to fail it is block-buffered stdout. Python buffers by 4 KiB
/// when stdout is a pipe, and a plugin that only prints then says nothing until
/// it exits: on a user's machine it sits at `Starting` for twenty seconds and
/// is killed with a diagnostic that names a timeout rather than a buffer. Every
/// SDK guards against it (`sys.stdout.reconfigure(line_buffering=True)`, and
/// `flush=True` on the startup prints), and nothing checked the guard.
///
/// stdout **or** stderr, because that is what the daemon accepts: both drains
/// share one `first_line` signal in `spawn_supervised`.
async fn first_line_check(first: &mut FirstOutput) -> (String, bool, String) {
    let name = "the plugin says something before the daemon gives up".to_string();
    match first.wait().await {
        Some((at, stream)) => (
            name,
            true,
            format!(
                "first line on {stream} after {at:.1?} (the daemon waits \
                 {PLUGIN_START_TIMEOUT_SECS}s, spec/limits.yaml plugin_start_timeout_secs)"
            ),
        ),
        None => (
            name,
            false,
            format!(
                "the plugin produced no output on stdout or stderr within \
                 {PLUGIN_START_TIMEOUT_SECS}s. That is the daemon's readiness signal: it waits \
                 for the child's first line before it will call the start successful, and kills \
                 the process group after this long with the failure classified `start_timeout`. \
                 The usual cause is a block-buffered stream — Python buffers stdout when it is a \
                 pipe unless the SDK reconfigures it, and a startup print without `flush=True` \
                 sits in that buffer until the process exits."
            ),
        ),
    }
}

/// How the `Shutdown` RPC itself answered, and how quickly.
///
/// Split out with [`shutdown_check`] so the two timings can be driven directly
/// by a test. The pair they replace shared one `elapsed`, which made the two
/// interesting states — *answered slowly* and *answered at once and then hung*
/// — print the same sentence.
fn shutdown_probe(
    sent: &Result<proto::Empty, tonic::Status>,
    acknowledged: Duration,
) -> (Status, String) {
    match sent {
        // A plugin that exits while answering `Shutdown` drops the response,
        // and tonic reports that as a broken transport. That is the *correct*
        // behaviour being reported as an error, so it is not one — what matters
        // is whether the process is gone, which is `shutdown_check`'s business.
        Err(s) if s.code() == tonic::Code::Unimplemented => {
            (Status::Unimplemented, "answered UNIMPLEMENTED".to_string())
        }
        _ => (Status::Ok, format!("acknowledged in {acknowledged:.1?}")),
    }
}

/// Did the process actually go, and how do the two timings read together?
///
/// **Both numbers, always, and never the same number twice.** `acknowledged` is
/// how long the RPC took; `waited` is how much longer the process then took to
/// go, measured from a **separate clock started after the acknowledgement**. A
/// plugin that answers in 120 ms and then wedges has a tiny first number and a
/// second one equal to the grace — and reporting one number for both described
/// it as a slow acknowledgement, which sent somebody looking inside the shutdown
/// handler for latency that was never there.
///
/// The two origins are why the parameters are `acknowledged` and `waited`
/// rather than `acknowledged` and `total`: there is no single `elapsed` a caller
/// could pass for both, so the bug cannot be rewritten by accident.
fn shutdown_check(exited: bool, acknowledged: Duration, waited: Duration) -> (String, bool, String) {
    let name = "Shutdown is honoured within the grace period".to_string();
    let total = acknowledged + waited;
    if exited {
        return (
            name,
            true,
            format!(
                "acknowledged in {acknowledged:.1?}, process gone {total:.1?} after Shutdown \
                 (grace is {PLUGIN_STOP_GRACE_SECS}s, spec/limits.yaml plugin_stop_grace_secs)"
            ),
        );
    }
    (
        name,
        false,
        format!(
            "Shutdown was acknowledged in {acknowledged:.1?} and the process was STILL RUNNING \
             {PLUGIN_STOP_GRACE_SECS}s later. The RPC returning is not the plugin stopping: \
             something after the acknowledgement is not finishing — a task that is not \
             cancelled, a thread that is not joined, a runtime that is not shut down. The daemon \
             kills the process group at the grace, so this plugin's tidy path never runs on a \
             user's machine (spec/limits.yaml plugin_stop_grace_secs)."
        ),
    )
}

/// The capabilities whose definitions the DAEMON renders — the declared plane.
///
/// A plugin that declares none of these contributes no labelled surface at all,
/// so the probe below is skipped rather than reporting an empty scan. Derived
/// from the manifest and not from a flag: an author cannot forget to pass it,
/// and a plugin that gains `actions` gains the probe with no edit.
const LABELLED_CAPABILITIES: &[&str] = &["actions", "triggers", "ui_contributions"];

/// **locale-round-trip** — drive every language and read what comes back.
///
/// `OnLanguageChanged` was driven with `"en"` and only ever `"en"`, at a plugin
/// whose default is `"en"`. A plugin with ten locales and a plugin with none
/// produced identical output, so nothing here had ever exercised the feature
/// this whole batch is about.
///
/// Two properties, and both are about what the PLUGIN returns rather than about
/// what a daemon would then render — this is a mock daemon, and asserting on a
/// rendered label would be asserting on our own resolver:
///
/// 1. **No unresolvable key.** A `$`-prefixed label whose key is in no locale
///    file reaches the user as the bare key, which reads on screen like a
///    deliberate identifier rather than a mistake. `$$` is the escape and is
///    not a key.
/// 2. **The declared plane is language-INVARIANT.** The daemon caches a
///    definition unresolved and resolves it per request, so a plugin must
///    return the same bytes whatever language it was last told about. A label
///    that changes between two passes is an author who called `t()` where they
///    needed `key()` — and on a real daemon that label is frozen in whichever
///    language won the race at startup, for as long as the definition is
///    cached.
///
/// Property 2 replaces the "label equals an `en.json` value" rule the plan
/// asked for, which cannot work: this repository's own scaffold deliberately
/// emits literal English labels that also appear in `en.json`, so that rule
/// would fail every fresh plugin `astra-plugin new` produces.
async fn locale_round_trip(
    client: &mut PluginCapabilityServiceClient<tonic::transport::Channel>,
    dir: &Path,
    declared: &BTreeSet<&str>,
) -> Vec<(String, bool, String)> {
    let name = "labels survive a language round trip".to_string();

    let labelled: Vec<&str> = LABELLED_CAPABILITIES
        .iter()
        .copied()
        .filter(|c| declared.contains(c))
        .collect();
    if labelled.is_empty() {
        return vec![(
            name,
            true,
            "skipped: this plugin declares no actions, triggers or ui_contributions, so it \
             contributes no label the daemon renders."
                .into(),
        )];
    }

    // The plugin's own locales/, read with the SDK's loader — the same one the
    // plugin process uses and the same rules the daemon's does.
    let i18n = astra_plugin_sdk::I18n::load(&dir.join("locales"));
    let english: BTreeSet<String> = locale_keys(dir, "en");

    // code -> (where, label), for every language in the vocabulary — including
    // the seven a realistic plugin has not translated, because that is where
    // the fallback lives.
    let mut seen: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    let mut definitions = 0usize;
    let mut slots = 0usize;

    for code in crate::locales::LOCALE_CODES {
        // Counted on the FIRST pass only. Summing across ten languages would
        // report "20 definitions" about a plugin with two, and a floor is worth
        // nothing if the number it floors is inflated tenfold.
        let counting = *code == crate::locales::LOCALE_CODES[0];
        // Optional hook: a plugin that does not serve it is not broken, and the
        // rest of the pass still says something.
        let _ = probe_call!(
            client,
            "OnLanguageChanged",
            on_language_changed(proto::LanguageChangedMsg { language: (*code).into() })
        );

        let mut per: BTreeMap<String, String> = BTreeMap::new();
        if declared.contains("actions")
            && let Ok(r) = probe_call!(client, "GetPluginActionTypes", get_plugin_action_types(proto::Empty {}))
        {
            if counting {
                definitions += r.types.len();
            }
            for ty in &r.types {
                per.insert(format!("action '{}' label", ty.r#type), ty.label.clone());
                per.insert(format!("action '{}' ai_description", ty.r#type), ty.ai_description.clone());
                if counting {
                    slots += 2;
                }
                collect_field_labels(&format!("action '{}'", ty.r#type), &ty.fields, &mut per, counting.then_some(&mut slots));
            }
        }
        if declared.contains("triggers")
            && let Ok(r) = probe_call!(client, "GetPluginTriggerTypes", get_plugin_trigger_types(proto::Empty {}))
        {
            if counting {
                definitions += r.types.len();
            }
            for ty in &r.types {
                per.insert(format!("trigger '{}' label", ty.r#type), ty.label.clone());
                if counting {
                    slots += 1;
                }
                collect_field_labels(&format!("trigger '{}'", ty.r#type), &ty.fields, &mut per, counting.then_some(&mut slots));
            }
        }
        if declared.contains("ui_contributions")
            && let Ok(r) = probe_call!(client, "GetUiContributions", get_ui_contributions(proto::Empty {}))
        {
            if counting {
                definitions += r.contributions.len();
            }
            for c in &r.contributions {
                per.insert(format!("ui contribution '{}' label", c.id), c.label.clone());
                if counting {
                    slots += 1;
                }
            }
        }
        seen.insert((*code).to_string(), per);
    }

    let mut out = Vec::new();
    let mut problems = round_trip_problems(&seen, &english);

    // The anti-vacuous guard. Two floors, because they fail for different
    // reasons: nothing came back at all, or something came back and this probe
    // stopped reading the fields off it.
    if definitions == 0 {
        problems.push(format!(
            "locale-round-trip got 0 definition(s) back across {} language(s) from a plugin that \
             declares {}. This probe now proves nothing — either those hooks return nothing, or \
             the probe has stopped matching them.",
            crate::locales::LOCALE_CODES.len(),
            labelled.join(", ")
        ));
    } else if slots == 0 {
        problems.push(format!(
            "locale-round-trip saw {definitions} definition(s) and examined 0 label field(s). \
             The definitions arrived and this probe read nothing off them, which is a broken \
             probe reporting a clean plugin."
        ));
    }

    // At most three examples and then a count: a plugin with forty labels and
    // one bad `en.json` would otherwise render its whole definition set at
    // somebody who wanted a verdict.
    let total = problems.len();
    if total > 3 {
        problems.truncate(3);
        problems.push(format!("…and {} further finding(s) not shown.", total - 3));
    }

    out.push(if problems.is_empty() {
        (
            name,
            true,
            format!(
                "{slots} label slot(s) on {definitions} definition(s), identical across all {} \
                 languages, every $key resolvable",
                crate::locales::LOCALE_CODES.len()
            ),
        )
    } else {
        (name, false, problems.join("  |  "))
    });

    // Whatever the loader could not use, said rather than swallowed. This is
    // where an author is told that `locales/zh-CN.json` will never be selected.
    //
    // ONLY when `locales/` exists. A plugin that ships no translations at all is
    // every plugin in the catalogue today, and `I18n::load` reports the missing
    // directory as a load error — which is correct for a loader and would be a
    // failed conformance run for a plugin that is doing nothing wrong. Whether
    // a plugin OUGHT to have a `locales/` is `astra-plugin check`'s N1, at
    // authoring time, as a note.
    if dir.join("locales").is_dir() {
        for e in i18n.load_errors() {
            out.push(("the plugin's locale files all load".into(), false, e.clone()));
        }
    }
    out
}

/// The two properties, over what came back — pure, so a test can drive it.
///
/// Property (1) is collapsed across languages before anything is printed. A
/// label is supposed to be language-invariant, so ONE misspelt key produces the
/// same finding ten times over, and ten identical paragraphs is an enumeration
/// wearing a report's clothes.
fn round_trip_problems(
    seen: &BTreeMap<String, BTreeMap<String, String>>,
    english: &BTreeSet<String>,
) -> Vec<String> {
    let mut problems = Vec::new();

    // (1) unresolvable keys.
    let mut unresolvable: BTreeMap<(&str, &str), Vec<&str>> = BTreeMap::new();
    for (code, per) in seen {
        for (at, value) in per {
            let Some(rest) = value.strip_prefix('$') else { continue };
            if rest.starts_with('$') {
                continue; // `$$` is the escape for a literal dollar.
            }
            if !english.contains(rest) {
                unresolvable
                    .entry((at.as_str(), value.as_str()))
                    .or_default()
                    .push(code.as_str());
            }
        }
    }
    for ((at, value), codes) in &unresolvable {
        problems.push(format!(
            "{at} came back as `{value}` under {} of the {} languages probed, and `{}` is in no \
             locale file. The daemon looks it up, finds nothing, and puts the bare key on the \
             user's screen — which reads like a deliberate identifier rather than a mistake.",
            codes.len(),
            crate::locales::LOCALE_CODES.len(),
            value.trim_start_matches('$'),
        ));
    }

    // (2) language invariance.
    let base = seen.get("en").cloned().unwrap_or_default();
    for (code, per) in seen {
        if code == "en" {
            continue;
        }
        for (at, value) in per {
            let Some(was) = base.get(at) else { continue };
            if was != value {
                problems.push(format!(
                    "{at} is {was:?} under `en` and {value:?} under `{code}`. The daemon caches a \
                     definition UNRESOLVED and resolves it per request, so a plugin must return \
                     the same bytes whatever language it was last told about — this one resolved \
                     it itself. Use `key(\"…\")` here and `t(\"…\")` only for strings this \
                     process prints."
                ));
            }
        }
    }
    problems
}

fn collect_field_labels(
    owner: &str,
    fields: &[proto::FieldDefinitionMsg],
    per: &mut BTreeMap<String, String>,
    mut slots: Option<&mut usize>,
) {
    for f in fields {
        per.insert(format!("{owner} field '{}' label", f.id), f.label.clone());
        per.insert(format!("{owner} field '{}' placeholder", f.id), f.placeholder.clone());
        per.insert(format!("{owner} field '{}' description", f.id), f.description.clone());
        if let Some(n) = slots.as_deref_mut() {
            *n += 3;
        }
        for (i, o) in f.options.iter().enumerate() {
            per.insert(format!("{owner} field '{}' option {i} label", f.id), o.label.clone());
            if let Some(n) = slots.as_deref_mut() {
                *n += 1;
            }
        }
    }
}

/// Every key in one `locales/<code>.json`, or nothing.
///
/// Read directly rather than through `I18n`, which exposes lookups and not the
/// key set of one specific language — and `en` is what property (1) is about.
fn locale_keys(dir: &Path, code: &str) -> BTreeSet<String> {
    std::fs::read_to_string(dir.join("locales").join(format!("{code}.json")))
        .ok()
        .and_then(|t| serde_json::from_str::<std::collections::HashMap<String, String>>(&t).ok())
        .map(|m| m.into_keys().collect())
        .unwrap_or_default()
}

/// What reached the daemon, and whether it was allowed to.
///
/// Everything else this command does drives the plugin inbound and reads the
/// answer, which means the whole plugin→daemon direction was invisible to it: a
/// host client that stopped sending `x-session-token` produced an
/// `UNAUTHENTICATED` for every `fire_trigger`, `log`, `get_config`,
/// `set_variable` and `push_to_ui` the plugin made, and this command still
/// printed `OK`. That is the Phase 0 state that made the protocol unusable in
/// all three languages, and it would have shipped again with a green gate on
/// it.
///
/// [`MockDaemon`] already records both halves; these two checks read them.
fn host_side_checks(daemon: &MockDaemon) -> Vec<(String, bool, String)> {
    let calls = daemon.recorded().calls();
    let refused = daemon.unauthenticated_calls();

    let reached = (
        "the plugin talked to the daemon".to_string(),
        !calls.is_empty(),
        if calls.is_empty() {
            "this plugin made no host calls at all, so nothing here could observe whether its \
             session token works. Every SDK routes its own log lines through `PluginLog`, so a \
             plugin that sends nothing is either not using the SDK's runner or has its logging \
             bridge switched off."
                .to_string()
        } else {
            format!("{} host call(s) reached the daemon: {}", calls.len(), summarise(&calls))
        },
    );

    let authenticated = (
        "every host call carried the session token".to_string(),
        refused.is_empty(),
        if refused.is_empty() {
            "no host call was refused for want of `x-session-token`".to_string()
        } else {
            format!(
                "{} host call(s) arrived without a valid `x-session-token` and were refused: {}. \
                 On a real daemon every one of those does nothing and the plugin is told so in a \
                 status it usually ignores — the tools still answer, the triggers never fire. The \
                 token is the one the daemon returns as `client_session_token` in the `Register` \
                 response; the host client has to attach it to every RPC but `Register`.",
                refused.len(),
                summarise(&refused),
            )
        },
    );

    vec![reached, authenticated]
}

/// `a, b, c` with repeats counted — a log line, not a transcript.
fn summarise(calls: &[String]) -> String {
    let mut counts: std::collections::BTreeMap<&str, usize> = std::collections::BTreeMap::new();
    for c in calls {
        *counts.entry(c.as_str()).or_default() += 1;
    }
    counts
        .into_iter()
        .map(|(name, n)| if n == 1 { name.to_string() } else { format!("{name}×{n}") })
        .collect::<Vec<_>>()
        .join(", ")
}

/// Call one hook with a request the daemon could plausibly send.
#[allow(clippy::too_many_arguments)]
async fn probe_one(
    client: &mut PluginCapabilityServiceClient<tonic::transport::Channel>,
    hook: &Hook,
    config_instance: &Value,
    tools: &[proto::PluginToolDef],
    actions: &[String],
    triggers: &[String],
    voices: &[String],
) -> (Status, String) {
    let rpc = hook.rpc.as_str();
    let result: Result<String, tonic::Status> = match rpc {
        "ListTools" => probe_call!(client, rpc, list_tools(proto::Empty {}))
            .map(|r| format!("{} tool(s)", r.tools.len())),
        "CallTool" => {
            let name = tools.first().map(|t| t.name.clone()).unwrap_or_default();
            if name.is_empty() {
                return (
                    Status::Error,
                    "ListTools returned no tools, so there is nothing to call. A plugin that \
                     declares `tools` and offers none is one the model can never use."
                        .into(),
                );
            }
            probe_call!(client, rpc, call_tool(proto::PluginCallToolRequest {
                    tool_name: name.clone(),
                    arguments_json: "{}".into(),
                }))
            .map(|r| {
                if r.success {
                    format!("`{name}` answered")
                } else {
                    // A tool that refuses empty arguments is a working tool.
                    format!("`{name}` answered with an in-band error: {}", brief(&r.error))
                }
            })
        }
        "TtsSynthesize" => probe_call!(client, rpc, tts_synthesize(proto::PluginTtsSynthesizeRequest {
                text: "Astra conformance probe.".into(),
                voice_id: voices.first().cloned().unwrap_or_default(),
                speed: 1.0,
                pitch: 1.0,
            }))
        .map(|r| format!("{} byte(s) of audio", r.audio_data.len())),
        "TtsListVoices" => probe_call!(client, rpc, tts_list_voices(proto::Empty {}))
            .map(|r| format!("{} voice(s)", r.voices.len())),
        "TtsGetConfigFields" => probe_call!(client, rpc, tts_get_config_fields(proto::Empty {}))
            .map(|r| format!("{} field(s)", r.config_fields.len())),
        "TtsActivate" => probe_call!(client, rpc, tts_activate(proto::PluginTtsActivateRequest {
                // Not a real content-encryption key: 32 zero bytes. A provider
                // that needs a real one refuses in band, which is an answer.
                cek: vec![0u8; 32],
                voice_id: voices.first().cloned().unwrap_or_default(),
            }))
        .map(|_| "activated".into()),
        "SttProcess" => return stt_process(client).await,
        "SttGetLanguages" => probe_call!(client, rpc, stt_get_languages(proto::Empty {}))
            .map(|r| format!("{} language(s)", r.languages.len())),
        "SttGetConfigFields" => probe_call!(client, rpc, stt_get_config_fields(proto::Empty {}))
            .map(|r| format!("{} field(s)", r.config_fields.len())),
        "SttLoad" => probe_call!(client, rpc, stt_load(proto::SttLoadRequest {
                model_path: String::new(),
                use_gpu: false,
            }))
        .map(|_| "loaded".into()),
        "SttUnload" => probe_call!(client, rpc, stt_unload(proto::Empty {}))
            .map(|_| "unloaded".into()),
        "SttGetLoadState" => probe_call!(client, rpc, stt_get_load_state(proto::Empty {}))
            .map(|r| format!("state = {}", r.state)),
        "AiComplete" => return ai_complete(client).await,
        "ExecuteAction" => {
            let action = actions.first().cloned().unwrap_or_default();
            if action.is_empty() {
                return (
                    Status::Error,
                    "GetPluginActionTypes returned nothing, so no action can be executed. A \
                     plugin that declares `actions` and defines none appears in the command \
                     editor as an empty list."
                        .into(),
                );
            }
            probe_call!(client, rpc, execute_action(proto::PluginExecuteActionRequest {
                    action_type: action.clone(),
                    params_json: "{}".into(),
                }))
            .map(|r| {
                if r.success {
                    format!("`{action}` ran")
                } else {
                    format!("`{action}` answered with an in-band error: {}", brief(&r.error))
                }
            })
        }
        "GetPluginActionTypes" => probe_call!(client, rpc, get_plugin_action_types(proto::Empty {}))
        .map(|r| format!("{} action type(s)", r.types.len())),
        "GetPluginTriggerTypes" => probe_call!(client, rpc, get_plugin_trigger_types(proto::Empty {}))
        .map(|r| format!("{} trigger type(s)", r.types.len())),
        "OnActiveTriggers" => probe_call!(client, rpc, on_active_triggers(proto::PluginActiveTriggersMsg {
                trigger_types: triggers.to_vec(),
            }))
        .map(|_| format!("accepted {} active trigger(s)", triggers.len())),
        "GetUiContributions" => probe_call!(client, rpc, get_ui_contributions(proto::Empty {}))
            .map(|r| format!("{} contribution(s)", r.contributions.len())),
        "CallFromUi" => probe_call!(client, rpc, call_from_ui(proto::PluginUiCallRequest {
                method: "__astra_conformance_probe".into(),
                params_json: "{}".into(),
            }))
        .map(|r| {
            if r.error.is_empty() {
                "answered".into()
            } else {
                // An unknown method rejected in band is exactly right: the
                // response carries `error`, the RPC itself succeeded.
                format!("rejected an unknown method in band: {}", brief(&r.error))
            }
        }),
        "OnConfigChanged" => probe_call!(client, rpc, on_config_changed(proto::PluginConfigChangedMsg {
                config_json: config_instance.to_string(),
            }))
        .map(|_| "accepted".into()),
        "OnLanguageChanged" => probe_call!(client, rpc, on_language_changed(proto::LanguageChangedMsg {
                language: "en".into(),
            }))
        .map(|_| "accepted".into()),
        "HealthCheck" => probe_call!(client, rpc, health_check(proto::Empty {}))
            .map(|r| format!("healthy = {}, status = {}", r.healthy, brief(&r.status))),
        other => {
            return (
                Status::Error,
                format!(
                    "{other}: this CLI has no probe for it. spec/hooks.yaml grew a `routing: live` \
                     hook that astra-plugin-cli/src/commands/test.rs does not know how to call."
                ),
            );
        }
    };

    classify(result)
}

fn classify(result: Result<String, tonic::Status>) -> (Status, String) {
    match result {
        Ok(detail) => (Status::Ok, detail),
        Err(s) if s.code() == tonic::Code::Unimplemented => {
            (Status::Unimplemented, "answered UNIMPLEMENTED".into())
        }
        Err(s) => (Status::Error, format!("{:?}: {}", s.code(), brief(s.message()))),
    }
}

/// `SttProcess`, driven with enough audio to reach the channel the daemon sizes
/// at `stt_audio_channel_capacity`.
///
/// The chunk count is not decoration. The motivating defect was an SDK-side
/// audio channel of 32 against a daemon-side 500, which truncated every
/// utterance at the smaller bound and looked, from outside, like a bad model.
/// A probe that sends three chunks cannot see it.
async fn stt_process(
    client: &mut PluginCapabilityServiceClient<tonic::transport::Channel>,
) -> (Status, String) {
    use astra_plugin_sdk::testing::fixtures;

    let pcm = fixtures::wake_seed_burst();
    let total = pcm.len();
    let chunks: Vec<proto::PluginAudioChunk> = pcm
        .into_iter()
        .enumerate()
        .map(|(i, data)| proto::PluginAudioChunk {
            data,
            is_last: i + 1 == total,
            // The daemon sets the rate on the first chunk only.
            sample_rate: if i == 0 { fixtures::SAMPLE_RATE } else { 0 },
            options: None,
        })
        .collect();
    let stream = async_stream_of(chunks);

    let call = client.stt_process(req(stream));
    let resp = match tokio::time::timeout(PROBE_TIMEOUT, call).await {
        Err(_) => return (Status::Error, format!("no response within {PROBE_TIMEOUT:?}")),
        Ok(Err(s)) if s.code() == tonic::Code::Unimplemented => {
            return (Status::Unimplemented, "answered UNIMPLEMENTED".into());
        }
        Ok(Err(s)) => return (Status::Error, format!("{:?}: {}", s.code(), brief(s.message()))),
        Ok(Ok(r)) => r,
    };

    let mut events = 0usize;
    let mut inbound = resp.into_inner();
    let drain = async {
        while let Ok(Some(_)) = inbound.message().await {
            events += 1;
        }
    };
    if tokio::time::timeout(PROBE_TIMEOUT, drain).await.is_err() {
        return (
            Status::Error,
            format!("the event stream did not end within {PROBE_TIMEOUT:?}"),
        );
    }
    // An empty stream is not an answer, and this is the case a `code() ==
    // Unimplemented` check cannot see. A recognizer that does not implement
    // transcription still *accepts* the `SttProcess` stream — the SDK's default
    // `stt_transcribe_stream` buffers every chunk, forwards to
    // `stt_transcribe`, gets the "hook absent" error back, and closes the
    // response stream. From the daemon's side that is a successful RPC that
    // transcribed nothing, which is exactly how a broken STT plugin presents to
    // a user: the microphone works, the waveform moves, and no text ever
    // appears. The contract is at least one `SttEvent::transcript` per
    // utterance.
    if events == 0 {
        return (
            Status::Error,
            format!(
                "{total} chunk(s) of audio went in and NO event came out. The RPC succeeded, so \
                 this is not an UNIMPLEMENTED — it is a recognizer that accepted an utterance and \
                 produced no transcript. Implement `stt_transcribe` (one call per utterance) or \
                 `stt_transcribe_stream` (partials as audio flows)."
            ),
        );
    }
    (
        Status::Ok,
        format!("{total} chunk(s) in, {events} event(s) out"),
    )
}

async fn ai_complete(
    client: &mut PluginCapabilityServiceClient<tonic::transport::Channel>,
) -> (Status, String) {
    let request = proto::PluginAiCompleteRequest {
        messages: vec![proto::PluginAiMessage {
            role: "user".into(),
            content: "ping".into(),
            ..Default::default()
        }],
        max_tokens: 16,
        ..Default::default()
    };
    let resp = match tokio::time::timeout(PROBE_TIMEOUT, client.ai_complete(req(request))).await {
        Err(_) => return (Status::Error, format!("no response within {PROBE_TIMEOUT:?}")),
        Ok(Err(s)) if s.code() == tonic::Code::Unimplemented => {
            return (Status::Unimplemented, "answered UNIMPLEMENTED".into());
        }
        Ok(Err(s)) => return (Status::Error, format!("{:?}: {}", s.code(), brief(s.message()))),
        Ok(Ok(r)) => r,
    };
    let mut chunks = 0usize;
    let mut inbound = resp.into_inner();
    let drain = async {
        while let Ok(Some(_)) = inbound.message().await {
            chunks += 1;
        }
    };
    if tokio::time::timeout(PROBE_TIMEOUT, drain).await.is_err() {
        return (
            Status::Error,
            format!("the completion stream did not end within {PROBE_TIMEOUT:?}"),
        );
    }
    // Same reasoning as `SttProcess`: an accepted request that streams nothing
    // back is a provider the chat loop waits on and gets a blank turn from. The
    // SDK appends the `Done` chunk itself, so even a provider that emits no
    // text sends one.
    if chunks == 0 {
        return (
            Status::Error,
            "the completion stream closed without a single chunk — not even the `Done` the SDK \
             appends. A provider that answers this way produces an empty assistant turn."
                .into(),
        );
    }
    (Status::Ok, format!("{chunks} chunk(s)"))
}

// ── the two schema assertions ────────────────────────────────────────────────

/// Every tool's `parameters_json` must parse, and its root must be an object
/// schema.
fn tool_schemas_check(tools: &[proto::PluginToolDef]) -> (String, bool, String) {
    let name = "tool schemas parse with an object root".to_string();
    let mut bad = Vec::new();
    for tool in tools {
        match schema_root_is_object(&tool.parameters_json) {
            Ok(()) => {}
            Err(why) => bad.push(format!("{}: {why}", tool.name)),
        }
    }
    if bad.is_empty() {
        (name, true, format!("{} tool schema(s) checked", tools.len()))
    } else {
        (name, false, bad.join("; "))
    }
}

fn config_schema_check(schema: Option<&Value>, instance: &Value) -> (String, bool, String) {
    let name = "config schema parses with an object root".to_string();
    match schema {
        None => (name, true, "no [config] section — nothing to check".into()),
        Some(s) => match schema_root_is_object(&s.to_string()) {
            Ok(()) => (
                name,
                true,
                format!(
                    "{} propert(ies), defaults: {}",
                    s.get("properties")
                        .and_then(Value::as_object)
                        .map(|p| p.len())
                        .unwrap_or(0),
                    instance
                ),
            ),
            Err(why) => (name, false, why),
        },
    }
}

/// The rule, in one place: a JSON Schema the daemon forwards to a model must be
/// an object schema.
fn schema_root_is_object(text: &str) -> Result<(), String> {
    if text.trim().is_empty() {
        return Err("the schema is empty. A tool with no schema is a tool the model calls with \
                    no arguments, which is rarely what was meant — write `{\"type\":\"object\", \
                    \"properties\":{}}` if it really takes none"
            .into());
    }
    let value: Value = serde_json::from_str(text).map_err(|e| format!("not valid JSON: {e}"))?;
    let Some(obj) = value.as_object() else {
        return Err("the schema's root is not a JSON object".into());
    };
    match obj.get("type").and_then(Value::as_str) {
        Some("object") => Ok(()),
        Some(other) => Err(format!(
            "the schema's root is `\"type\": \"{other}\"`. Arguments arrive as a JSON object, so \
             the root must be `\"object\"`"
        )),
        None => Err("the schema's root has no `\"type\"`. It must be `\"object\"`".into()),
    }
}

/// A JSON instance built from a schema's declared defaults.
///
/// Deliberately shallow — `default` on each top-level property, and nothing
/// invented for the ones that have none. Guessing a value for an undeclared
/// property would make the round trip test this function rather than the
/// author's schema.
fn defaults_from_schema(schema: &Value) -> Value {
    let mut out = serde_json::Map::new();
    if let Some(props) = schema.get("properties").and_then(Value::as_object) {
        for (key, spec) in props {
            if let Some(default) = spec.get("default") {
                out.insert(key.clone(), default.clone());
            }
        }
    }
    Value::Object(out)
}

// ── process and transport plumbing ───────────────────────────────────────────

/// When the child first said anything, and on which stream.
///
/// The daemon's readiness signal is exactly this: `spawn_supervised` drains
/// stdout and stderr into one `first_line` oneshot and gives the plugin
/// `PLUGIN_START_TIMEOUT` to fill it (`astra-daemon/src/process/supervisor.rs`,
/// `astra-daemon/src/plugins/instance.rs`). A plugin that registers but never
/// produces a line is a plugin the daemon kills before it gets that far.
#[derive(Clone)]
struct FirstOutput {
    at: tokio::sync::watch::Receiver<Option<(Duration, &'static str)>>,
    spawned: Instant,
}

impl FirstOutput {
    /// Wait for the first line, up to the daemon's own start timeout measured
    /// from the spawn. `None` means the plugin never said anything in time.
    async fn wait(&mut self) -> Option<(Duration, &'static str)> {
        let deadline = self.spawned + Duration::from_secs(PLUGIN_START_TIMEOUT_SECS);
        loop {
            if let Some(seen) = *self.at.borrow_and_update() {
                return Some(seen);
            }
            let left = deadline.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return None;
            }
            match tokio::time::timeout(left, self.at.changed()).await {
                Ok(Ok(())) => {}
                // Both relays are gone: the process closed its pipes without
                // ever writing a line.
                Ok(Err(_)) => return *self.at.borrow(),
                Err(_) => return None,
            }
        }
    }
}

/// Start the plugin the way the daemon starts it.
fn spawn_plugin(
    dir: &Path,
    manifest: &astra_plugin_manifest::PluginManifest,
    daemon_addr: &str,
    spawn_token: &str,
    capabilities: &[String],
) -> Result<(Child, FirstOutput)> {
    let entry_command = manifest.entry.command.clone();
    let command = entry_command.as_str();
    if command.trim().is_empty() {
        anyhow::bail!("plugin.toml has no entry.command, so there is nothing to start");
    }

    let mut args = manifest.entry.args.clone();
    args.push(format!("--daemon-addr={daemon_addr}"));
    args.push(format!("--plugin-id={}", manifest.plugin.id));
    args.push(format!("--auth-token={spawn_token}"));
    if !capabilities.is_empty() {
        args.push(format!("--capabilities={}", capabilities.join(",")));
    }

    // Same resolution rule as `dev --standalone`: a command with a separator is
    // a path inside the plugin directory, a bare word is a PATH lookup.
    let program: PathBuf = if command.contains('/') || command.contains('\\') {
        let joined = dir.join(command);
        // A manifest written on Linux says `target/release/foo`; on Windows the
        // file is `foo.exe`. The daemon applies the same fallback.
        if !joined.is_file() && !std::env::consts::EXE_SUFFIX.is_empty() {
            let with_suffix = dir.join(format!("{command}{}", std::env::consts::EXE_SUFFIX));
            if with_suffix.is_file() {
                with_suffix
            } else {
                joined
            }
        } else {
            joined
        }
    } else {
        PathBuf::from(command)
    };

    hprintln!("  Starting: {} {}", program.display(), args.join(" "));
    tracing::debug!(
        program = %program.display(),
        args = ?args,
        cwd = %dir.display(),
        "spawning the plugin the way the daemon would"
    );

    let mut proc = Command::new(&program);
    proc
        .args(&args)
        // The daemon states capabilities in the environment too — an SDK old
        // enough to reject unknown argv reads them there. Passing both is what
        // the daemon does.
        .env("ASTRA_PLUGIN_CAPABILITIES", capabilities.join(","))
        // …and the daemon tells the plugin that it authenticates the calls it
        // makes in, so the plugin may refuse the ones that are not. `MockDaemon`
        // presents the same `--auth-token` on every call (see `req`), so this
        // harness enforces exactly what production does. Without it the plugin
        // sits in the SDKs' `warn` stage, and a capability server that would
        // refuse the real daemon — a token compared wrongly, an interceptor an
        // author disabled — passes here and fails on a user's machine.
        .env("ASTRA_PLUGIN_CAPABILITY_AUTH", "require")
        .current_dir(dir)
        // BOTH streams are piped, and neither is inherited. The plugin's own
        // output is the author's most useful diagnostic and it is relayed line
        // by line below — but it is also the *readiness signal the daemon
        // reads*, and an inherited stream is one this process never sees. Under
        // `--json` both go to stderr, because stdout carries exactly one JSON
        // object and nothing else; in human mode stdout stays stdout, so
        // interleaving with the progress lines still reads the way it did.
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);

    let spawned = Instant::now();
    let mut child = proc
        .spawn()
        .with_context(|| {
            format!(
                "Failed to start '{}'. entry.command is `{command}` — does that file exist? \
                 Run `astra-plugin build` first, or drop --no-build.",
                program.display()
            )
        })?;

    let (first_tx, first_rx) = tokio::sync::watch::channel(None);
    let first_tx = std::sync::Arc::new(first_tx);

    let relay = |reader: Option<tokio::process::ChildStdout>,
                     err: Option<tokio::process::ChildStderr>,
                     stream: &'static str| {
        let first_tx = first_tx.clone();
        tokio::spawn(async move {
            use tokio::io::{AsyncBufReadExt, BufReader};
            let mut lines: Box<dyn tokio::io::AsyncBufRead + Unpin + Send> = match (reader, err) {
                (Some(out), _) => Box::new(BufReader::new(out)),
                (_, Some(e)) => Box::new(BufReader::new(e)),
                _ => return,
            };
            let mut buf = String::new();
            loop {
                buf.clear();
                match lines.read_line(&mut buf).await {
                    Ok(0) | Err(_) => break,
                    Ok(_) => {}
                }
                first_tx.send_if_modified(|slot| {
                    if slot.is_none() {
                        *slot = Some((spawned.elapsed(), stream));
                        true
                    } else {
                        false
                    }
                });
                let line = buf.trim_end_matches(['\n', '\r']);
                if stream == "stdout" && !crate::output::json_mode() {
                    println!("{line}");
                } else {
                    eprintln!("{line}");
                }
            }
        });
    };
    relay(child.stdout.take(), None, "stdout");
    relay(None, child.stderr.take(), "stderr");

    Ok((child, FirstOutput { at: first_rx, spawned }))
}

/// Wait for the plugin to `Register`, racing it against the process dying.
async fn await_registration(daemon: &MockDaemon, child: &mut Child) -> Result<u16> {
    let deadline = tokio::time::sleep(Duration::from_secs(PLUGIN_START_TIMEOUT_SECS));
    tokio::pin!(deadline);
    loop {
        if let Some(reg) = daemon.registration() {
            return Ok(reg.port as u16);
        }
        tokio::select! {
            biased;
            exit = child.wait() => {
                anyhow::bail!(
                    "the plugin process exited before it registered ({}). Its output is above; \
                     the usual causes are a missing runtime, a panic in `on_start`, or an SDK \
                     that rejected an argument the daemon passes.",
                    match exit { Ok(s) => s.to_string(), Err(e) => e.to_string() }
                );
            }
            _ = &mut deadline => {
                anyhow::bail!(
                    "the plugin did not register within {PLUGIN_START_TIMEOUT_SECS}s \
                     (spec/limits.yaml plugin_start_timeout_secs). The daemon gives it exactly \
                     this long before calling the start a failure."
                );
            }
            _ = tokio::time::sleep(Duration::from_millis(10)) => {}
        }
    }
}

async fn connect(port: u16) -> Result<PluginCapabilityServiceClient<tonic::transport::Channel>> {
    let addr = format!("http://127.0.0.1:{port}");
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        match PluginCapabilityServiceClient::connect(addr.clone()).await {
            Ok(c) => return Ok(c),
            Err(e) if Instant::now() >= deadline => {
                return Err(anyhow::Error::new(e).context(format!(
                    "could not reach the plugin's own gRPC server on {addr}, which is the port it \
                     put in its Register"
                )));
            }
            Err(_) => tokio::time::sleep(Duration::from_millis(50)).await,
        }
    }
}

/// The token `MockDaemon` minted for this run, as `--auth-token` on argv and as
/// `x-plugin-token` on every call back in. Owned by [`MockDaemon`]; latched here
/// so [`req`] can stay a plain function.
static SPAWN_TOKEN: OnceLock<&'static str> = OnceLock::new();

/// A request carrying the token the daemon presents to a plugin.
///
/// Without it a plugin built with `CapabilityAuth::Require` answers
/// `UNAUTHENTICATED` to everything, and every hook would be reported as broken.
fn req<T>(message: T) -> tonic::Request<T> {
    let mut r = tonic::Request::new(message);
    if let Some(token) = SPAWN_TOKEN.get() {
        r.metadata_mut()
            .insert(astra_plugin_sdk::wire::PLUGIN_TOKEN_HEADER, token.parse().expect("ascii token"));
    }
    r
}

fn async_stream_of(
    chunks: Vec<proto::PluginAudioChunk>,
) -> impl tokio_stream::Stream<Item = proto::PluginAudioChunk> + Send + 'static {
    tokio_stream::iter(chunks)
}

/// One line, bounded — a plugin's error message can be a stack trace.
fn brief(s: &str) -> String {
    let line = s.lines().next().unwrap_or("").trim();
    if line.chars().count() > 160 {
        format!("{}…", line.chars().take(160).collect::<String>())
    } else {
        line.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The vendored hook list must be byte-identical to the generated one.
    ///
    /// Vendoring is what lets `astra-plugin test` run in an author's project,
    /// where `spec/` does not exist. This is the price: a check that the copy
    /// did not rot. Skipped when the repo is not around (a published crate),
    /// which is the only case where there is nothing to compare against.
    #[test]
    fn the_vendored_conformance_list_matches_the_spec() {
        let generated = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("spec/generated/conformance.json");
        if !generated.exists() {
            eprintln!("skipped: {} is not present", generated.display());
            return;
        }
        let upstream = std::fs::read_to_string(&generated).unwrap();
        assert_eq!(
            upstream.replace("\r\n", "\n"),
            CONFORMANCE_JSON.replace("\r\n", "\n"),
            "astra-plugin-cli/src/conformance.json has drifted from \
             spec/generated/conformance.json. Re-copy it: \
             `cp spec/generated/conformance.json astra-plugin-cli/src/conformance.json`"
        );
    }

    /// The token check has to fail when the token is missing, and pass when it
    /// is there. Driven against a real `MockDaemon` over loopback, because the
    /// thing under test is a header on the wire.
    #[tokio::test]
    async fn the_host_side_checks_read_what_the_daemon_recorded() {
        use astra_plugin_sdk::proto::plugin_host_service_client::PluginHostServiceClient;

        let daemon = MockDaemon::start().await.unwrap();
        let mut client = PluginHostServiceClient::connect(format!("http://{}", daemon.addr()))
            .await
            .unwrap();
        let line = || proto::PluginLogRequest {
            plugin_id: "under-test".into(),
            level: "info".into(),
            message: "hello".into(),
        };

        // Nothing said yet: "talked to the daemon" fails, the token check has
        // nothing to complain about.
        let checks = host_side_checks(&daemon);
        assert_eq!(checks.len(), 2);
        assert!(!checks[0].1, "no calls yet: {}", checks[0].2);
        assert!(checks[1].1, "no calls means no refusals: {}", checks[1].2);

        // A call with the token the daemon issued: both pass.
        let mut ok = tonic::Request::new(line());
        ok.metadata_mut()
            .insert(astra_plugin_sdk::wire::SESSION_TOKEN_HEADER, daemon.session_token().parse().unwrap());
        client.plugin_log(ok).await.unwrap();
        let checks = host_side_checks(&daemon);
        assert!(checks[0].1, "{}", checks[0].2);
        assert!(checks[1].1, "{}", checks[1].2);

        // The Phase 0 regression: a call with no token at all. The plugin
        // "talked to the daemon" either way — what changes is that the daemon
        // refused, and that is the check that has to go red.
        client
            .plugin_log(tonic::Request::new(line()))
            .await
            .expect_err("the mock daemon refuses an untokened host call");
        let checks = host_side_checks(&daemon);
        assert!(checks[0].1, "{}", checks[0].2);
        assert!(!checks[1].1, "an unauthenticated host call must fail the check");
        assert!(checks[1].2.contains("log"), "{}", checks[1].2);
    }

    /// The two shutdown states must not print the same sentence.
    ///
    /// The bug: `elapsed` was taken AFTER `timeout(grace, child.wait())`, and
    /// then used for both the probe's "acknowledged in {elapsed}" and the
    /// check's "the process exited {elapsed} after Shutdown". A plugin that
    /// answered in 120 ms and then hung was therefore reported as
    /// *"acknowledged in 5.0s"* — a slow handler, which is a completely
    /// different defect with a completely different fix. It cost a real
    /// investigation: a flake read as latency inside the shutdown handler when
    /// the handler had returned instantly and the process was wedged after it.
    #[test]
    fn a_hung_plugin_does_not_read_as_a_slow_acknowledgement() {
        let quick = Duration::from_millis(120);
        let grace = Duration::from_secs(PLUGIN_STOP_GRACE_SECS);

        // Answered at once, then hung: 120 ms of RPC and a full grace of
        // waiting. This is the case that used to lie.
        let (_, ok, hung) = shutdown_check(false, quick, grace);
        assert!(!ok);
        assert!(hung.contains("120.0ms"), "the ACK time must survive: {hung}");
        assert!(hung.contains("STILL RUNNING"), "{hung}");
        assert!(
            !hung.contains("acknowledged in 5.0s"),
            "this is the exact sentence the bug printed: {hung}"
        );

        // Answered at once and exited at once — the healthy case.
        let (_, ok, fine) = shutdown_check(true, quick, Duration::from_millis(20));
        assert!(ok);
        assert!(fine.contains("120.0ms") && fine.contains("140.0ms"), "{fine}");
        // 120 ms of RPC plus 20 ms of waiting: the TOTAL is derived, never passed.

        // A genuinely slow acknowledgement, which is the state the bug's
        // message CLAIMED. It has to be distinguishable from the first case,
        // and the two share no wording that would let them be confused.
        let slow = Duration::from_millis(4_800);
        let (_, ok, slow_ack) = shutdown_check(true, slow, Duration::from_millis(100));
        assert!(ok);
        assert!(slow_ack.contains("4.8s"), "{slow_ack}");
        assert_ne!(slow_ack, hung);
        assert!(!slow_ack.contains("STILL RUNNING"), "{slow_ack}");

        // The probe line carries the ACK only: it is about the RPC, and the
        // process's fate is the check's business.
        let (status, detail) = shutdown_probe(&Ok(proto::Empty {}), quick);
        assert_eq!(status, Status::Ok);
        assert_eq!(detail, "acknowledged in 120.0ms");
        let (status, detail) =
            shutdown_probe(&Err(tonic::Status::unimplemented("no")), quick);
        assert_eq!(status, Status::Unimplemented);
        assert_eq!(detail, "answered UNIMPLEMENTED");
    }

    /// `$$` is the daemon's escape and is never a key — including here, where
    /// property (1) of `locale-round-trip` would otherwise fail a plugin whose
    /// label is legitimately "$5 and up".
    #[test]
    fn the_round_trip_reads_locale_keys_off_disk_and_honours_the_escape() {
        let dir = std::env::temp_dir().join(format!("astra-rt-keys-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(dir.join("locales")).unwrap();
        std::fs::write(
            dir.join("locales/en.json"),
            r#"{"action.roll.label":"Roll","listing.name":"X"}"#,
        )
        .unwrap();

        let keys = locale_keys(&dir, "en");
        assert!(keys.contains("action.roll.label"), "{keys:?}");
        assert!(locale_keys(&dir, "ru").is_empty(), "an absent locale has no keys");

        // The same predicate the probe applies, spelled out here so the escape
        // cannot be quietly dropped from it.
        for (label, is_key) in [
            ("$action.roll.label", true),
            ("$$5 and up", false),
            ("Roll", false),
        ] {
            let looks = label
                .strip_prefix('$')
                .is_some_and(|rest| !rest.starts_with('$'));
            assert_eq!(looks, is_key, "{label}");
        }
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// The two properties `locale-round-trip` asserts, and the one shape it
    /// must NOT report ten times.
    ///
    /// Verified against a live plugin too — a `.with_label(&self.i18n.t(…))`
    /// on the companion example produced exactly the property-2 finding, and a
    /// `key("ui.cat.labl")` with no such key produced property 1. What that run
    /// also produced was the same paragraph ten times over, once per language,
    /// which is what the collapse below exists to stop.
    #[test]
    fn the_round_trip_collapses_a_finding_that_is_true_in_every_language() {
        let english: BTreeSet<String> = ["ui.cat.label".to_string()].into_iter().collect();

        let mut seen: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
        for code in crate::locales::LOCALE_CODES {
            let mut per = BTreeMap::new();
            // A misspelt key, invariant across languages — which is what a
            // correctly written declared-plane label looks like.
            per.insert("ui 'cat' label".to_string(), "$ui.cat.labl".to_string());
            // …and one that resolves, plus the `$$` escape, neither of which
            // may be reported at all.
            per.insert("ui 'cat' hint".to_string(), "$ui.cat.label".to_string());
            per.insert("ui 'cat' price".to_string(), "$$5 and up".to_string());
            seen.insert((*code).to_string(), per);
        }

        let problems = round_trip_problems(&seen, &english);
        assert_eq!(
            problems.len(),
            1,
            "one misspelt key must produce ONE finding, not one per language:\n{}",
            problems.join("\n")
        );
        assert!(problems[0].contains("10 of the 10 languages"), "{}", problems[0]);
        assert!(problems[0].contains("ui.cat.labl"), "{}", problems[0]);
        assert!(!problems[0].contains("$5 and up"), "the `$$` escape is not a key");

        // Property 2: a label that changes between languages.
        seen.get_mut("ru")
            .unwrap()
            .insert("ui 'cat' label".to_string(), "$ui.cat.labl.ru".to_string());
        let problems = round_trip_problems(&seen, &english);
        assert!(
            problems.iter().any(|p| p.contains("under `ru`") && p.contains("resolved \
                 it itself")),
            "a label that differs between two passes is the `t()`-instead-of-`key()` \
             defect:\n{}",
            problems.join("\n")
        );

        // A plugin whose labels are plain English and language-invariant says
        // nothing at all — the case every scaffold produces.
        let mut clean: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
        for code in crate::locales::LOCALE_CODES {
            clean.insert(
                (*code).to_string(),
                [("ui 'cat' label".to_string(), "Companion Cat".to_string())]
                    .into_iter()
                    .collect(),
            );
        }
        assert!(round_trip_problems(&clean, &english).is_empty());
    }

    #[test]
    fn the_call_summary_counts_repeats() {
        assert_eq!(summarise(&[]), "");
        assert_eq!(
            summarise(&[
                "log".to_string(),
                "fire_trigger".to_string(),
                "log".to_string()
            ]),
            "fire_trigger, log×2",
        );
    }

    #[test]
    fn every_live_hook_has_a_probe() {
        // The engine's coverage, asserted rather than assumed: a hook added to
        // the spec with no arm in `probe_one` must fail here, not on an
        // author's machine as "this CLI has no probe for it".
        const PROBED: &[&str] = &[
            "ListTools",
            "CallTool",
            "TtsSynthesize",
            "TtsListVoices",
            "TtsGetConfigFields",
            "TtsActivate",
            "SttProcess",
            "SttGetLanguages",
            "SttGetConfigFields",
            "SttLoad",
            "SttUnload",
            "SttGetLoadState",
            "AiComplete",
            "ExecuteAction",
            "GetPluginActionTypes",
            "GetPluginTriggerTypes",
            "OnActiveTriggers",
            "GetUiContributions",
            "CallFromUi",
            "OnConfigChanged",
            "OnLanguageChanged",
            "HealthCheck",
            "Shutdown",
        ];
        let missing: Vec<String> = conformance_hooks()
            .unwrap()
            .into_iter()
            .filter(|h| !PROBED.contains(&h.rpc.as_str()))
            .map(|h| h.rpc)
            .collect();
        assert!(
            missing.is_empty(),
            "spec/generated/conformance.json lists hook(s) `astra-plugin test` cannot call: {missing:?}"
        );
    }

    /// The two hooks this engine drives as streams, and the two the spec says
    /// are streams, must be the same two.
    ///
    /// A unary probe against a streaming rpc does not fail loudly — tonic
    /// answers, the CLI records "ok", and the streaming path is never
    /// exercised. That is the level-2 blind spot the wire harness exists to
    /// close, so it is asserted rather than assumed.
    #[test]
    fn the_streaming_probes_are_the_streaming_hooks() {
        const STREAMED_HERE: &[&str] = &["SttProcess", "AiComplete"];
        let streamed_in_spec: Vec<String> = conformance_hooks()
            .unwrap()
            .into_iter()
            .filter(|h| h.streaming != "unary")
            .map(|h| h.rpc)
            .collect();
        let mut expected: Vec<String> = STREAMED_HERE.iter().map(|s| s.to_string()).collect();
        expected.sort();
        let mut actual = streamed_in_spec;
        actual.sort();
        assert_eq!(
            actual, expected,
            "spec/hooks.yaml and this engine disagree about which live hooks stream"
        );
    }

    #[test]
    fn required_and_optional_are_read_from_the_spec_not_hardcoded() {
        let hooks = conformance_hooks().unwrap();
        let list_tools = hooks.iter().find(|h| h.rpc == "ListTools").unwrap();
        let tts_activate = hooks.iter().find(|h| h.rpc == "TtsActivate").unwrap();
        assert!(list_tools.required, "ListTools is `required` in spec/hooks.yaml");
        assert!(
            !tts_activate.required,
            "TtsActivate is `optional` in spec/hooks.yaml — the exemption that keeps a scaffold \
             declaring every capability from looking broken"
        );
        assert!(hooks.iter().any(|h| h.teardown && h.rpc == "Shutdown"));
    }

    #[test]
    fn an_object_schema_is_the_only_acceptable_root() {
        assert!(schema_root_is_object(r#"{"type":"object","properties":{}}"#).is_ok());
        assert!(schema_root_is_object("").is_err());
        assert!(schema_root_is_object("not json").is_err());
        assert!(schema_root_is_object(r#"["a"]"#).is_err());
        assert!(schema_root_is_object(r#"{"type":"string"}"#).is_err());
        assert!(schema_root_is_object(r#"{"properties":{}}"#).is_err());
    }

    #[test]
    fn defaults_come_from_the_schema_and_nowhere_else() {
        let schema = json!({
            "type": "object",
            "properties": {
                "sides": { "type": "integer", "default": 20 },
                "api_key": { "type": "string" }
            }
        });
        // `api_key` has no default and is NOT invented: a made-up value would
        // make the round trip a test of this function.
        assert_eq!(defaults_from_schema(&schema), json!({ "sides": 20 }));
    }

    #[test]
    fn a_required_unimplemented_hook_is_a_failure_and_an_optional_one_is_not() {
        let findings = Findings {
            plugin_id: "p".into(),
            language: "rust".into(),
            capabilities: vec!["tts".into()],
            probes: vec![
                Probe {
                    rpc: "TtsSynthesize".into(),
                    capability: "tts".into(),
                    required: true,
                    status: Status::Unimplemented,
                    detail: "answered UNIMPLEMENTED".into(),
                },
                Probe {
                    rpc: "TtsActivate".into(),
                    capability: "tts".into(),
                    required: false,
                    status: Status::Unimplemented,
                    detail: "answered UNIMPLEMENTED".into(),
                },
            ],
            checks: vec![],
        };
        let failures = findings.failures();
        assert_eq!(failures.len(), 1, "only the required hook fails: {failures:?}");
        assert!(failures[0].starts_with("TtsSynthesize:"));
    }
}

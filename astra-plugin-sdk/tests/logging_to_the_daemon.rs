//! §5.10, Rust half: the author's own `tracing` reaches the user's log pane.
//!
//! One test, because a `tracing` subscriber is process-global and installing
//! two of them is a race rather than a test. Everything the layer has to get
//! right is asserted here in one pass.

use std::time::{Duration, Instant};

use astra_plugin_sdk::testing::{LogLine, RecordingHost};
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

/// Poll until the daemon has `n` log lines, or fail — the shipper is a task,
/// so the assertion has to wait for it rather than assume a scheduling order.
async fn wait_for(host: &RecordingHost, n: usize) -> Vec<LogLine> {
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        let logs = host.logs();
        if logs.len() >= n {
            return logs;
        }
        assert!(
            Instant::now() < deadline,
            "waited 5s for {n} log lines; got {logs:?}",
        );
        tokio::time::sleep(Duration::from_millis(5)).await;
    }
}

#[tokio::test(flavor = "multi_thread")]
async fn tracing_becomes_plugin_log_and_panics_arrive_at_error_level() {
    let host = RecordingHost::new("dice-roller");

    // What `run_with` installs, minus the stderr layer.
    tracing_subscriber::registry()
        .with(astra_plugin_sdk::logging::layer())
        .init();

    // Nothing ships before a host exists — which is the honest answer, because
    // before registration there is nowhere to ship to.
    tracing::info!("before attach");
    tokio::time::sleep(Duration::from_millis(50)).await;
    assert!(
        host.logs().is_empty(),
        "there was no daemon yet: {:?}",
        host.logs()
    );

    astra_plugin_sdk::logging::attach(host.clone());

    // ── the author's own log line, with the daemon's level names ──
    tracing::info!("rolled {} dice", 3);
    let logs = wait_for(&host, 1).await;
    assert_eq!(logs[0].level, "info");
    assert_eq!(logs[0].message, "rolled 3 dice");

    tracing::warn!(retry = 2, "provider is slow");
    let logs = wait_for(&host, 2).await;
    assert_eq!(logs[1].level, "warn");
    assert_eq!(
        logs[1].message, "provider is slow retry=2",
        "structured fields have to survive; the pane is a string",
    );

    // ── what must NOT ship ──
    tracing::debug!("chatter");
    tracing::trace!("more chatter");
    // Shipping a log line is an RPC, and an RPC that logs is a log line. If the
    // transport stack's own events shipped, this would be a loop.
    tracing::warn!(target: "h2", "stream reset");
    tracing::error!(target: "tonic::transport", "connection error");
    tokio::time::sleep(Duration::from_millis(100)).await;
    assert_eq!(
        host.logs().len(),
        2,
        "only the plugin's own INFO-and-above lines: {:?}",
        host.logs()
    );

    // ── a panic reports itself, caught or not ──
    astra_plugin_sdk::panics::install_hook();
    let panicked = astra_plugin_sdk::panics::catch("call_tool", async {
        panic!("this tool has a bug")
    })
    .await
    .expect_err("the panic is caught");
    assert!(panicked.message.contains("this tool has a bug"));

    let logs = wait_for(&host, 3).await;
    let report = &logs[2];
    assert_eq!(
        report.level, "error",
        "a panic is reported at the highest level there is",
    );
    assert!(
        report.message.contains("plugin panicked: this tool has a bug"),
        "{report:?}",
    );
    assert!(
        report.message.contains("location=") && report.message.contains("logging_to_the_daemon.rs"),
        "the report has to say which line to open: {report:?}",
    );

    // ── and the plugin is still running ──
    tracing::info!("still here");
    let logs = wait_for(&host, 4).await;
    assert_eq!(logs[3].message, "still here");

    assert_eq!(
        astra_plugin_sdk::logging::dropped(),
        0,
        "nothing was dropped for a full queue in this test",
    );
}

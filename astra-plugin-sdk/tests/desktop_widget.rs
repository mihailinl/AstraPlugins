// SPDX-License-Identifier: MPL-2.0
use astra_plugin_sdk::prelude::*;
use astra_plugin_sdk::proto;
use astra_plugin_sdk::testing::Harness;
use prost::Message;
#[derive(Default)]
struct Legacy;
#[astra::plugin]
impl Legacy {
    #[hook]
    async fn handle_ui_call(
        &self,
        _ctx: &PluginContext,
        method: &str,
        _params: &str,
    ) -> Result<String, ToolError> {
        Ok(method.into())
    }
}
#[derive(Default)]
struct Contextual;
#[astra::plugin]
impl Contextual {
    #[hook]
    async fn handle_widget_ui_call(
        &self,
        _ctx: &PluginContext,
        _method: &str,
        _params: &str,
        widget: Option<&WidgetContext>,
    ) -> Result<String, ToolError> {
        Ok(widget.map(|w| w.instance_id.clone()).unwrap_or_default())
    }
}
#[tokio::test]
async fn contextual_hook_and_legacy_default_dispatch() {
    let legacy = Harness::new(Legacy).start().await.unwrap();
    assert_eq!(legacy.ui_call("ping", json!({})).await.unwrap(), "ping");
    let contextual = Harness::new(Contextual).start().await.unwrap();
    for id in ["first", "second"] {
        let widget = WidgetContext {
            instance_id: id.into(),
            ..Default::default()
        };
        assert_eq!(
            contextual
                .widget_ui_call("ping", json!({}), &widget)
                .await
                .unwrap(),
            id
        );
    }
}
#[test]
fn nested_descriptor_roundtrip() {
    let value = UiContribution::widget(
        "counter",
        "Counter",
        DesktopWidget::new(vec![
            WidgetFormat::new("list", "List", "index.html", 4, 3)
                .with_limits(3, 2, 8, 6)
                .with_readable_size(220, 120),
        ])
        .repeatable()
        .with_surfaces(vec![
            WidgetSurface::modal("settings", "Settings", "index.html").with_size(480, 320),
        ])
        .with_fields(vec![
            FieldDef::text("title", "Title").with_default("Counter"),
        ])
        .with_settings_surface("settings"),
    );
    let decoded = proto::PluginUiContribution::decode(value.encode_to_vec().as_slice()).unwrap();
    assert_eq!(decoded, value);
    assert_eq!(decoded.slot, "desktop.widget");
}

// WireHarness disables tracing initialization, so no tracing event can satisfy
// this assertion. Lifecycle registration still uses the authenticated host RPC.
#[tokio::test]
async fn quiet_runner_records_authenticated_startup() {
    let wire = astra_plugin_sdk::testing::WireHarness::start(Contextual)
        .await
        .unwrap();
    let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(5);
    loop {
        let logs = wire.logs();
        if logs.iter().any(|line| {
            line.level == "info"
                && line
                    .message
                    .starts_with("Plugin 'test-plugin' registered on port ")
        }) {
            break;
        }
        assert!(
            tokio::time::Instant::now() < deadline,
            "no startup host record: {logs:?}"
        );
        tokio::time::sleep(std::time::Duration::from_millis(5)).await;
    }
    assert!(wire.daemon().recorded().unauthenticated_calls().is_empty());
    wire.shutdown().await.unwrap();
}

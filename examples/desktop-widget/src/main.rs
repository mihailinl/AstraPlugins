use astra_plugin_sdk::prelude::*;

#[derive(Default)]
struct DesktopWidgetDemo;

#[astra::plugin]
impl DesktopWidgetDemo {
    #[hook]
    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![UiContribution::widget("counter", "Instance counter",
            DesktopWidget::new(vec![
                WidgetFormat::new("compact", "Compact", "index.html", 2, 2).with_limits(2, 2, 4, 3).with_readable_size(120, 90),
                WidgetFormat::new("list", "List", "index.html", 4, 3).with_limits(3, 2, 8, 6).with_readable_size(220, 120),
            ]).repeatable().with_surfaces(vec![
                WidgetSurface::popover("menu", "Counter menu", "index.html").with_size(280, 220),
                WidgetSurface::modal("details", "Counter details", "index.html").with_size(480, 320),
                WidgetSurface::modal("settings", "Counter settings", "index.html").with_size(480, 360),
            ]).with_fields(vec![
                FieldDef::text("title", "Title").with_default("My counter"),
                FieldDef::dropdown("color", "Color", &[("default", "Default"), ("accent", "Accent")]).with_default("default"),
                FieldDef::number("limit", "Count limit").with_default("100").with_min(1.0).with_max(1000.0).with_step(1.0),
            ]).with_settings_surface("settings"))]
    }

    #[hook]
    async fn handle_widget_ui_call(&self, _ctx: &PluginContext, method: &str, _params_json: &str, widget: Option<&WidgetContext>) -> Result<String, ToolError> {
        if method != "ping" { return Err(ToolError::NotFound(method.into())); }
        // Instance context arrives automatically, without a global config mutation.
        Ok(json!({"ok": true, "instance": widget.map(|w| &w.instance_id)}).to_string())
    }

}

astra::main!(DesktopWidgetDemo::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    /// `cargo test`. The harness runs the hooks in process against a recording
    /// host: no daemon, no socket, no Astra installed.
    ///
    /// `h.host().fired_triggers()` / `.logs()` / `.variables()` say what the
    /// plugin told Astra; `h.host().deny("fire_trigger")` stages the refusal a
    /// user's `[permissions]` would produce. For the wire — registration, the
    /// session token, streaming audio — there is
    /// `astra_plugin_sdk::testing::WireHarness`.
    #[tokio::test]
    async fn it_starts_and_answers() {
        let h = Harness::new(DesktopWidgetDemo::default())
            .with_config(json!({}))
            .start()
            .await
            .expect("the plugin started");

        assert!(h.health().await.0);
    }
}

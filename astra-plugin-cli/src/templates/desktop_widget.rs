//! Desktop widget scaffold; UI shell, settings draft and instance isolation belong to Astra.
use anyhow::Result;
use std::{fs, path::Path};
pub fn generate_frontend(out: &Path, frontend: &str) -> Result<()> {
    if frontend == "react" {
        fs::write(
            out.join("frontend/App.tsx"),
            include_str!("../../resources/desktop-widget/App.tsx"),
        )?;
    } else {
        fs::write(
            out.join("ui/main.js"),
            include_str!("../../resources/desktop-widget/main.js"),
        )?;
    }
    Ok(())
}
pub const RUST: &str = r##"    #[hook]
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
"##;
pub const PYTHON: &str = r#"
    async def get_ui_contributions(self):
        return [UiContribution.widget("counter", "Instance counter", DesktopWidget(
            repeatable=True,
            formats=[
                WidgetFormat(id="compact", label="Compact", url="index.html", default_w=2, default_h=2, min_w=2, min_h=2, max_w=4, max_h=3, min_pixel_width=120, min_pixel_height=90),
                WidgetFormat(id="list", label="List", url="index.html", default_w=4, default_h=3, min_w=3, min_h=2, max_w=8, max_h=6, min_pixel_width=220, min_pixel_height=120),
            ], surfaces=[
                WidgetSurface.popover("menu", "Counter menu", "index.html", width=280, height=220),
                WidgetSurface.modal("details", "Counter details", "index.html", width=480, height=320),
                WidgetSurface.modal("settings", "Counter settings", "index.html", width=480, height=360),
            ], config_fields=[
                Field.text("title", "Title", default="My counter"),
                Field.dropdown("color", "Color", options=[("default", "Default"), ("accent", "Accent")], default="default"),
                Field.number("limit", "Count limit", default="100", min=1, max=1000, step=1),
            ], settings_surface="settings"))]

    async def handle_widget_ui_call(self, method, params_json, widget):
        if method == "ping":
            return {"ok": True, "instance": widget.instance_id if widget else None}
        return await self.handle_ui_call(method, params_json)
"#;
pub const TYPESCRIPT: &str = r#"
  ui: {
    contributions: [UiContrib.widget("counter", "Instance counter", {
      repeatable: true,
      formats: [
        {id:"compact", label:"Compact", url:"index.html", defaultW:2, defaultH:2, minW:2, minH:2, maxW:4, maxH:3, minPixelWidth:120, minPixelHeight:90},
        {id:"list", label:"List", url:"index.html", defaultW:4, defaultH:3, minW:3, minH:2, maxW:8, maxH:6, minPixelWidth:220, minPixelHeight:120},
      ], surfaces: [
        {id:"menu", label:"Counter menu", url:"index.html", kind:"popover", width:280, height:220},
        {id:"details", label:"Counter details", url:"index.html", kind:"modal", width:480, height:320},
        {id:"settings", label:"Counter settings", url:"index.html", kind:"modal", width:480, height:360},
      ], configFields: [
        Field.text("title", "Title", {default:"My counter"}),
        Field.dropdown("color", "Color", {options:[["default","Default"],["accent","Accent"]], default:"default"}),
        Field.number("limit", "Count limit", {default:"100", min:1, max:1000, step:1}),
      ], settingsSurface:"settings",
    })],
    onWidgetCall: {ping: (_params, widget) => ({ok:true, instance:widget?.instanceId ?? null})},
  },
"#;

// SPDX-License-Identifier: MPL-2.0
// Copyright (C) 2026 Minice — https://minice.ai
//! Desktop widget builders. Grid geometry is measured in cells; surface geometry in pixels.
use crate::{DesktopWidget, FieldDef, UiContribution, WidgetFormat, WidgetSurface};
impl UiContribution {
    pub fn widget(id: impl Into<String>, label: impl Into<String>, widget: DesktopWidget) -> Self {
        let url = widget
            .formats
            .first()
            .map(|f| f.url.clone())
            .unwrap_or_default();
        Self {
            id: id.into(),
            label: label.into(),
            slot: "desktop.widget".into(),
            url,
            transparent: true,
            pointer_events: true,
            desktop_widget: Some(widget),
            ..Default::default()
        }
    }
}
impl DesktopWidget {
    pub fn new(formats: Vec<WidgetFormat>) -> Self {
        Self {
            formats,
            ..Default::default()
        }
    }
    pub fn repeatable(mut self) -> Self {
        self.repeatable = true;
        self
    }
    pub fn with_surfaces(mut self, surfaces: Vec<WidgetSurface>) -> Self {
        self.surfaces = surfaces;
        self
    }
    pub fn with_fields(mut self, fields: Vec<FieldDef>) -> Self {
        self.config_fields = fields;
        self
    }
    pub fn with_settings_surface(mut self, id: impl Into<String>) -> Self {
        self.settings_surface = id.into();
        self
    }
}
impl WidgetFormat {
    pub fn new(
        id: impl Into<String>,
        label: impl Into<String>,
        url: impl Into<String>,
        width: u32,
        height: u32,
    ) -> Self {
        Self {
            id: id.into(),
            label: label.into(),
            url: url.into(),
            appearance: "card".into(),
            default_w: width,
            default_h: height,
            min_w: 1,
            min_h: 1,
            ..Default::default()
        }
    }
    pub fn with_limits(mut self, min_w: u32, min_h: u32, max_w: u32, max_h: u32) -> Self {
        self.min_w = min_w;
        self.min_h = min_h;
        self.max_w = max_w;
        self.max_h = max_h;
        self
    }
    pub fn with_preview(mut self, url: impl Into<String>) -> Self {
        self.preview_url = url.into();
        self
    }
    pub fn with_appearance(mut self, appearance: impl Into<String>) -> Self {
        self.appearance = appearance.into();
        self
    }
    pub fn fixed(mut self) -> Self {
        self.fixed_size = true;
        self
    }
    pub fn with_readable_size(mut self, width: u32, height: u32) -> Self {
        self.min_pixel_width = width;
        self.min_pixel_height = height;
        self
    }
}
impl WidgetSurface {
    pub fn popover(
        id: impl Into<String>,
        label: impl Into<String>,
        url: impl Into<String>,
    ) -> Self {
        Self {
            id: id.into(),
            label: label.into(),
            url: url.into(),
            kind: "popover".into(),
            ..Default::default()
        }
    }
    pub fn modal(id: impl Into<String>, label: impl Into<String>, url: impl Into<String>) -> Self {
        Self {
            kind: "modal".into(),
            ..Self::popover(id, label, url)
        }
    }
    pub fn with_size(mut self, width: u32, height: u32) -> Self {
        self.width = width;
        self.height = height;
        self
    }
    pub fn with_limits(
        mut self,
        min_width: u32,
        min_height: u32,
        max_width: u32,
        max_height: u32,
    ) -> Self {
        self.min_width = min_width;
        self.min_height = min_height;
        self.max_width = max_width;
        self.max_height = max_height;
        self
    }
}

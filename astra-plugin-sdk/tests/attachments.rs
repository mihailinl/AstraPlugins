// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! **A tool can ask for the pictures the person attached, and read them.**
//!
//! Two halves, each at both harness levels: a tool's `wants_attachments` must
//! reach `ListTools` (and stay `false` on every tool that never heard of it),
//! and the pictures on `PluginCallToolRequest.attachments` must reach
//! `ctx.attachments()` with their bytes, type and name intact — on that call
//! only.
//!
//! Level 2 is the one that can fail in silence: the runner has to move the
//! field out of the decoded request onto the handler's context, and a runner
//! that forgot to would produce a plugin that declares the flag, is granted the
//! permission, and never sees a picture.

use astra_plugin_sdk::prelude::*;
use astra_plugin_sdk::testing::{Harness, WireHarness};

const PNG: &[u8] = &[0x89, b'P', b'N', b'G', 0x0d, 0x0a, 0x1a, 0x0a, 0, 1, 2, 255];
const JPEG: &[u8] = &[0xff, 0xd8, 0xff, 0xe0, 7, 7, 7];

fn sent() -> Vec<AiImage> {
    vec![
        AiImage {
            mime_type: "image/png".into(),
            data: PNG.to_vec(),
            filename: "cat.png".into(),
        },
        AiImage {
            mime_type: "image/jpeg".into(),
            data: JPEG.to_vec(),
            filename: "dog.jpg".into(),
        },
    ]
}

/// What a handler saw, as one comparable string: type, name and every byte.
fn describe(images: &[AiImage]) -> String {
    images
        .iter()
        .map(|i| format!("{}|{}|{:?}", i.mime_type, i.filename, i.data))
        .collect::<Vec<_>>()
        .join(";")
}

// ── a hand-written plugin ────────────────────────────────────────────────────

/// `describe` asks for pictures and reports them; `plain` never heard of them.
struct Photos;

#[async_trait]
impl PluginCapability for Photos {
    type Config = NoConfig;

    async fn list_tools(&self) -> Vec<ToolDef> {
        vec![
            ToolDef::new("describe", "Describe the pictures the person attached.")
                .with_attachments(true),
            ToolDef::new("plain", "Written before the flag existed."),
        ]
    }

    async fn call_tool(
        &self,
        ctx: &PluginContext,
        name: &str,
        _arguments_json: &str,
    ) -> Result<String, ToolError> {
        match name {
            "describe" => Ok(describe(ctx.attachments())),
            "plain" => Ok(format!("plain:{}", ctx.attachments().len())),
            other => Err(ToolError::NotFound(format!("no tool named `{other}`"))),
        }
    }
}

fn flags(tools: Vec<ToolDef>) -> Vec<(String, bool)> {
    tools
        .into_iter()
        .map(|t| (t.name, t.wants_attachments))
        .collect()
}

// ── level 1 ──────────────────────────────────────────────────────────────────

#[tokio::test]
async fn the_flag_reaches_list_tools_and_defaults_to_false() {
    let h = Harness::new(Photos).start().await.unwrap();
    assert_eq!(
        flags(h.tools().await),
        [("describe".to_string(), true), ("plain".to_string(), false)]
    );
}

#[tokio::test]
async fn attachments_reach_the_handler_with_bytes_type_and_name_intact() {
    let h = Harness::new(Photos).start().await.unwrap();
    let out = h
        .call_tool_with_attachments("describe", json!({}), Some("conv-1"), sent())
        .await
        .unwrap();
    assert_eq!(out, describe(&sent()));
}

#[tokio::test]
async fn a_tool_without_the_flag_still_works_and_a_plain_call_reads_nothing() {
    let h = Harness::new(Photos).start().await.unwrap();
    assert_eq!(h.call_tool("plain", json!({})).await.unwrap(), "plain:0");
    assert_eq!(
        h.call_tool("describe", json!({})).await.unwrap(),
        "",
        "a call that carries no pictures reads an empty slice"
    );
}

// ── level 2 ──────────────────────────────────────────────────────────────────

#[tokio::test]
async fn over_the_wire_the_flag_is_in_list_tools() {
    let w = WireHarness::start(Photos).await.unwrap();
    assert_eq!(
        flags(w.list_tools().await.unwrap()),
        [("describe".to_string(), true), ("plain".to_string(), false)]
    );
}

#[tokio::test]
async fn over_the_wire_the_pictures_reach_the_handler_intact() {
    let w = WireHarness::start(Photos).await.unwrap();
    let r = w
        .call_tool_with_attachments("describe", "{}", Some("conv-7"), sent())
        .await
        .unwrap();
    assert!(r.success, "{}", r.error);
    assert_eq!(r.result, describe(&sent()));
}

#[tokio::test]
async fn over_the_wire_one_calls_pictures_never_reach_the_next() {
    // The runner scopes the pictures onto ONE call's context; the context it
    // clones the next call's from must never have held them.
    let w = WireHarness::start(Photos).await.unwrap();
    w.call_tool_with_attachments("describe", "{}", Some("conv-1"), sent())
        .await
        .unwrap();
    let next = w
        .call_tool_from("describe", "{}", Some("conv-1"))
        .await
        .unwrap();
    assert_eq!(next.result, "");
    let plain = w.call_tool("plain", "{}").await.unwrap();
    assert!(plain.success, "{}", plain.error);
    assert_eq!(plain.result, "plain:0");
}

// ── the macro ────────────────────────────────────────────────────────────────

#[derive(Default)]
struct MacroPhotos;

#[astra::plugin]
impl MacroPhotos {
    /// Count the pictures the person attached.
    #[tool(wants_attachments)]
    async fn count_photos(&self, ctx: &PluginContext) -> Result<String, ToolError> {
        Ok(ctx.attachments().len().to_string())
    }

    /// Written before the flag existed.
    #[tool]
    async fn older(&self, ctx: &PluginContext) -> Result<String, ToolError> {
        Ok(format!("older:{}", ctx.attachments().len()))
    }
}

#[tokio::test]
async fn the_macro_declares_the_flag_and_its_handler_reads_the_pictures() {
    let w = WireHarness::start(MacroPhotos).await.unwrap();
    let mut seen = flags(w.list_tools().await.unwrap());
    seen.sort();
    assert_eq!(
        seen,
        [("count_photos".to_string(), true), ("older".to_string(), false)]
    );
    let r = w
        .call_tool_with_attachments("count_photos", "{}", Some("conv-2"), sent())
        .await
        .unwrap();
    assert_eq!(r.result, "2");
    let r = w.call_tool("older", "{}").await.unwrap();
    assert_eq!(r.result, "older:0");
}

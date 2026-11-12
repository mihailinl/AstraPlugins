// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.
//
// Copyright (C) 2026 Minice — https://minice.ai

//! **An image provider draws one picture, or says in band why it did not.**
//!
//! The contract Astra reads (`image_gen/plugin.rs`, from `21790d761`): a
//! refusal the plugin means — `quota`, `rate_limited`, `not_configured`,
//! `unavailable`, `refused` — is an ANSWER in `error_code`, never a status,
//! because the daemon tries the person's own provider on the first four and
//! gives up on a plugin that errors. `ImageGetModels` is optional, and an
//! absent one must be `UNIMPLEMENTED` — the daemon's word for "no list", after
//! which it never sends this provider a picture to edit.
//!
//! Level 2 is the half that can fail in silence: the runner has to move the
//! pictures to edit out of the decoded request into the hook, and turn the
//! hook's answer into exactly one `PluginImage`.

use astra_plugin_sdk::HookUnimplemented;
use astra_plugin_sdk::prelude::*;
use astra_plugin_sdk::proto;
use astra_plugin_sdk::testing::{Harness, WireHarness};

const PNG: &[u8] = &[0x89, b'P', b'N', b'G', 0x0d, 0x0a, 0x1a, 0x0a, 0, 1, 2, 255];
const JPEG: &[u8] = &[0xff, 0xd8, 0xff, 0xe0, 7, 7, 7];
const WEBP: &[u8] = b"RIFF\x10\0\0\0WEBPVP8 ";

fn cat() -> AiImage {
    AiImage {
        mime_type: "image/jpeg".into(),
        data: JPEG.to_vec(),
        filename: "cat.jpg".into(),
    }
}

// ── a hand-written provider ──────────────────────────────────────────────────

/// Draws a PNG for any prompt, refuses by keyword, and reports what it was
/// asked in the caption so the test can read the request back.
struct Painter;

#[async_trait]
impl PluginCapability for Painter {
    type Config = NoConfig;

    async fn image_generate(
        &self,
        _ctx: &PluginContext,
        req: ImageRequest,
    ) -> anyhow::Result<ImageResponse> {
        Ok(match req.prompt.as_str() {
            "spent" => ImageResponse::refuse(ImageErrorCode::Quota, "monthly allowance used"),
            "slow" => {
                ImageResponse::refuse(ImageErrorCode::RateLimited, "slow down").with_retry_after(7)
            }
            "nope" => ImageResponse::refuse(ImageErrorCode::Refused, "the prompt was declined"),
            "keyless" => ImageResponse::refuse(ImageErrorCode::NotConfigured, "no API key set"),
            "down" => ImageResponse::refuse(ImageErrorCode::Unavailable, "the service is down"),
            "broken" => anyhow::bail!("the API answered garbage"),
            "nothing" => ImageResponse::drawn(Vec::new()),
            _ => ImageResponse::drawn(PNG).with_caption(format!(
                "ratio={} model={} inputs={}",
                req.aspect_ratio.as_deref().unwrap_or("-"),
                req.model,
                req.input_images
                    .iter()
                    .map(|i| format!("{}:{}:{}", i.mime_type, i.filename, i.data.len()))
                    .collect::<Vec<_>>()
                    .join(",")
            )),
        })
    }

    async fn image_models(
        &self,
        _ctx: &PluginContext,
    ) -> anyhow::Result<(Vec<ImageModelInfo>, String)> {
        Ok((
            vec![
                ImageModelInfo::new("draw-1", "Draw 1"),
                ImageModelInfo::new("edit-1", "Edit 1").accepts_input_images(),
            ],
            "edit-1".into(),
        ))
    }
}

/// A provider that draws and lists nothing: `ImageGetModels` is optional.
struct NoList;

#[async_trait]
impl PluginCapability for NoList {
    type Config = NoConfig;

    async fn image_generate(
        &self,
        _ctx: &PluginContext,
        _req: ImageRequest,
    ) -> anyhow::Result<ImageResponse> {
        Ok(ImageResponse::drawn(WEBP))
    }
}

/// Not an image provider at all.
struct Silent;

#[async_trait]
impl PluginCapability for Silent {
    type Config = NoConfig;
}

fn wire_request(prompt: &str) -> proto::PluginImageGenerateRequest {
    proto::PluginImageGenerateRequest {
        prompt: prompt.into(),
        ..Default::default()
    }
}

// ── the types ────────────────────────────────────────────────────────────────

#[test]
fn a_pictures_type_is_read_from_its_bytes() {
    assert_eq!(ImageResponse::mime_type_of(PNG), Some("image/png"));
    assert_eq!(ImageResponse::mime_type_of(JPEG), Some("image/jpeg"));
    assert_eq!(ImageResponse::mime_type_of(WEBP), Some("image/webp"));
    assert_eq!(
        ImageResponse::mime_type_of(b"GIF89a"),
        None,
        "the daemon refuses a GIF"
    );
    assert_eq!(ImageResponse::mime_type_of(b""), None);
    assert!(matches!(
        ImageResponse::drawn(PNG),
        ImageResponse::Drawn { ref mime_type, .. } if mime_type == "image/png"
    ));
    assert!(matches!(
        ImageResponse::drawn(b"???".to_vec()).with_mime_type("image/png"),
        ImageResponse::Drawn { ref mime_type, .. } if mime_type == "image/png"
    ));
}

#[test]
fn every_refusal_code_has_the_spelling_the_daemon_reads() {
    for (code, wire) in [
        (ImageErrorCode::Quota, "quota"),
        (ImageErrorCode::RateLimited, "rate_limited"),
        (ImageErrorCode::NotConfigured, "not_configured"),
        (ImageErrorCode::Unavailable, "unavailable"),
        (ImageErrorCode::Refused, "refused"),
    ] {
        assert_eq!(code.as_str(), wire);
        assert_eq!(code.to_string(), wire);
    }
    assert_eq!(
        ImageResponse::drawn(PNG).with_retry_after(9),
        ImageResponse::drawn(PNG),
        "a retry-after on a picture is a no-op"
    );
}

#[test]
fn a_request_built_by_hand_keeps_an_empty_ratio_as_none() {
    let req = ImageRequest::new("a fox")
        .with_aspect_ratio(" 16:9 ")
        .with_model("draw-1")
        .with_input_image(cat());
    assert_eq!(req.aspect_ratio.as_deref(), Some("16:9"));
    assert_eq!(req.model, "draw-1");
    assert_eq!(req.input_images.len(), 1);
    assert_eq!(
        ImageRequest::new("x").with_aspect_ratio("").aspect_ratio,
        None
    );
    assert!(ImageRequest::ASPECT_RATIOS.contains(&"3:4"));
}

// ── level 1 ──────────────────────────────────────────────────────────────────

#[tokio::test]
async fn the_harness_answers_what_the_hook_answered() {
    let h = Harness::new(Painter).start().await.unwrap();
    let drawn = h
        .image_generate(ImageRequest::new("a fox").with_aspect_ratio("4:3"))
        .await
        .unwrap();
    assert_eq!(
        drawn,
        ImageResponse::drawn(PNG).with_caption("ratio=4:3 model= inputs=")
    );
    assert_eq!(
        h.image_generate(ImageRequest::new("nope")).await.unwrap(),
        ImageResponse::refuse(ImageErrorCode::Refused, "the prompt was declined")
    );
    let (models, default_model) = h.image_models().await.unwrap();
    assert_eq!(default_model, "edit-1");
    assert_eq!(
        models
            .iter()
            .map(|m| (m.id.as_str(), m.accepts_input_images))
            .collect::<Vec<_>>(),
        [("draw-1", false), ("edit-1", true)]
    );
}

#[tokio::test]
async fn at_level_1_an_absent_hook_is_hook_unimplemented() {
    let h = Harness::new(NoList).start().await.unwrap();
    let e = h.image_models().await.unwrap_err();
    assert!(
        e.downcast_ref::<HookUnimplemented>().is_some(),
        "an absent image_models must be UNIMPLEMENTED, got {e:?}"
    );
    let h = Harness::new(Silent).start().await.unwrap();
    let e = h.image_generate(ImageRequest::new("x")).await.unwrap_err();
    assert!(e.downcast_ref::<HookUnimplemented>().is_some(), "{e:?}");
}

// ── level 2 ──────────────────────────────────────────────────────────────────

#[tokio::test]
async fn over_the_wire_one_picture_arrives_with_its_type_and_caption() {
    let w = WireHarness::start(Painter).await.unwrap();
    let r = w
        .client()
        .image_generate(w.request(proto::PluginImageGenerateRequest {
            prompt: "a fox".into(),
            aspect_ratio: "16:9".into(),
            model: "edit-1".into(),
            input_images: vec![cat()],
        }))
        .await
        .unwrap()
        .into_inner();
    assert_eq!(r.error_code, "");
    assert_eq!(r.images.len(), 1, "exactly one picture");
    assert_eq!(r.images[0].data, PNG);
    assert_eq!(r.images[0].mime_type, "image/png", "read from the bytes");
    assert_eq!(
        r.caption, "ratio=16:9 model=edit-1 inputs=image/jpeg:cat.jpg:7",
        "the ratio, the model and the picture to edit reached the hook intact"
    );
}

#[tokio::test]
async fn over_the_wire_an_empty_ratio_reaches_the_hook_as_none() {
    let w = WireHarness::start(Painter).await.unwrap();
    let r = w
        .client()
        .image_generate(w.request(wire_request("a fox")))
        .await
        .unwrap()
        .into_inner();
    assert_eq!(r.caption, "ratio=- model= inputs=");
}

#[tokio::test]
async fn over_the_wire_every_refusal_is_an_answer_not_a_status() {
    let w = WireHarness::start(Painter).await.unwrap();
    for (prompt, code, message, retry) in [
        ("spent", "quota", "monthly allowance used", 0),
        ("slow", "rate_limited", "slow down", 7),
        ("nope", "refused", "the prompt was declined", 0),
        ("keyless", "not_configured", "no API key set", 0),
        ("down", "unavailable", "the service is down", 0),
    ] {
        let r = w
            .client()
            .image_generate(w.request(wire_request(prompt)))
            .await
            .unwrap_or_else(|s| panic!("`{prompt}` must be an answer, got the status {s:?}"))
            .into_inner();
        assert!(r.images.is_empty(), "a refusal carries no picture");
        assert_eq!(r.error_code, code);
        assert_eq!(r.error_message, message);
        assert_eq!(r.retry_after_secs, retry);
    }
}

#[tokio::test]
async fn over_the_wire_an_err_is_a_status_and_not_a_refusal() {
    let w = WireHarness::start(Painter).await.unwrap();
    let s = w
        .client()
        .image_generate(w.request(wire_request("broken")))
        .await
        .unwrap_err();
    assert_eq!(s.code(), tonic::Code::Internal);
    assert!(s.message().contains("garbage"), "{}", s.message());

    // An empty picture is neither a picture nor a refusal: the SDK answers it
    // as a status, which the daemon reads as an outage and falls back from.
    let s = w
        .client()
        .image_generate(w.request(wire_request("nothing")))
        .await
        .unwrap_err();
    assert_eq!(s.code(), tonic::Code::Internal);
}

#[tokio::test]
async fn over_the_wire_the_model_list_says_which_model_edits() {
    let w = WireHarness::start(Painter).await.unwrap();
    let list = w
        .client()
        .image_get_models(w.request(proto::Empty {}))
        .await
        .unwrap()
        .into_inner();
    assert_eq!(list.default_model, "edit-1");
    assert_eq!(list.models.len(), 2);
    assert_eq!(list.models[0].name, "Draw 1");
    assert!(!list.models[0].accepts_input_images);
    assert!(list.models[1].accepts_input_images);
}

#[tokio::test]
async fn over_the_wire_an_absent_model_list_is_unimplemented() {
    let w = WireHarness::start(NoList).await.unwrap();
    let s = w
        .client()
        .image_get_models(w.request(proto::Empty {}))
        .await
        .unwrap_err();
    assert_eq!(
        s.code(),
        tonic::Code::Unimplemented,
        "the daemon reads UNIMPLEMENTED as `no list`; anything else is a broken plugin"
    );
    // ... and the provider still draws.
    let r = w
        .client()
        .image_generate(w.request(wire_request("a fox")))
        .await
        .unwrap()
        .into_inner();
    assert_eq!(r.images[0].mime_type, "image/webp");
}

#[tokio::test]
async fn over_the_wire_a_plugin_that_does_not_draw_is_unimplemented() {
    let w = WireHarness::start(Silent).await.unwrap();
    let s = w
        .client()
        .image_generate(w.request(wire_request("a fox")))
        .await
        .unwrap_err();
    assert_eq!(s.code(), tonic::Code::Unimplemented);
}

// ── the macro ────────────────────────────────────────────────────────────────

#[derive(Default)]
struct MacroPainter;

#[astra::plugin]
impl MacroPainter {
    #[hook]
    async fn image_generate(
        &self,
        _ctx: &PluginContext,
        req: ImageRequest,
    ) -> anyhow::Result<ImageResponse> {
        Ok(ImageResponse::drawn(PNG).with_caption(req.prompt))
    }
}

#[tokio::test]
async fn the_macro_declares_image_provider_and_the_hook_draws() {
    assert!(
        <MacroPainter as DeclaredCapabilities>::CAPS.contains(&"image_provider"),
        "a #[hook] image_generate declares the capability: {:?}",
        <MacroPainter as DeclaredCapabilities>::CAPS
    );
    let w = WireHarness::start(MacroPainter).await.unwrap();
    let r = w
        .client()
        .image_generate(w.request(wire_request("a fox")))
        .await
        .unwrap()
        .into_inner();
    assert_eq!(r.caption, "a fox");
}

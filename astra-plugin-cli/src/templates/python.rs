//! Python plugin project templates.

/// Turn `my-plugin` into `MyPlugin`.
fn class_name(name: &str) -> String {
    name.split('-')
        .map(|w| {
            let mut c = w.chars();
            match c.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().to_string() + c.as_str(),
            }
        })
        .collect::<Vec<_>>()
        .join("")
}

pub fn generate_plugin_py(name: &str, capabilities: &[&str]) -> String {
    let class_name = class_name(name);

    // Imported names, in the order the SDK's own docs use them. A scaffold that
    // imports something it does not use trains the author to ignore lint.
    let mut imports = vec!["Plugin"];
    let mut methods = String::new();

    if capabilities.contains(&"tools") {
        imports.push("tool");
        // `@tool`, not a `list_tools` returning dicts. The decorator reads the
        // method's type hints to build the JSON Schema the model is shown, so
        // the schema and the signature cannot drift apart — and dicts where a
        // capability type is expected are deprecated (removed in 0.7).
        methods.push_str(
            r#"
    @tool("Greet someone by name.")
    async def hello(self, name: str, excited: bool = False):
        # The parameters above ARE the schema: `name` is required because it has
        # no default, `excited` is optional because it has one. Returning a plain
        # value is enough — the SDK wraps it as a successful tool result.
        return f"Hello, {name}{'!' if excited else '.'}"
"#,
        );
    }

    if capabilities.contains(&"tts") {
        imports.push("VoiceInfo");
        methods.push_str(
            r#"
    async def tts_list_voices(self):
        return [
            VoiceInfo(
                id="default",
                name="Default Voice",
                language="en",
                gender="neutral",
            )
        ]

    async def tts_synthesize(self, text: str, voice_id: str, speed: float, pitch: float):
        # A placeholder that ANSWERS: 200 ms of 16 kHz silence, so a freshly
        # scaffolded plugin passes `astra-plugin test` on the first run. Raising
        # here instead would make the scaffold fail the project's own
        # conformance suite before the author had written a line.
        # TODO: synthesize `text` and put the PCM in `audio_data`.
        return {
            "audio_data": b"\x00\x00" * 3200,
            "format": "pcm_s16le",
            "sample_rate": 16000,
            "duration_ms": 200,
        }
"#,
        );
    }

    // `--template stt-streaming` asks for the streaming hook instead of the
    // unary one. Same capability — there is only one STT capability — but the
    // hook an author starts from decides whether their plugin can ever emit a
    // partial result, and bolting `stt_transcribe_stream` onto a finished unary
    // implementation is the retrofit people get subtly wrong.
    if capabilities.contains(&crate::commands::create::STREAMING_MARKER) {
        methods.push_str(
            r#"
    async def stt_get_languages(self):
        return ["en"]

    async def stt_transcribe_stream(self, audio, options=None):
        # An async GENERATOR: consume `audio` and yield results as you have
        # them. Yield `{"text": ..., "is_final": False}` for a partial the user
        # sees while still speaking, and one `is_final` result before returning.
        #
        # Back-pressure is real: the SDK buffers at most
        # `limits.STT_AUDIO_CHANNEL_CAPACITY` chunks — the same bound the daemon
        # uses — and the daemon dumps its whole wake-word pre-roll in at once.
        # Read in a loop; never block on anything slow between reads.
        # TODO: feed each chunk to your recognizer.
        chunks = 0
        async for chunk in audio:
            chunks += 1
        yield {"text": f"[{chunks} chunks]", "is_final": True}
"#,
        );
    } else if capabilities.contains(&"stt") {
        methods.push_str(
            r#"
    async def stt_get_languages(self):
        return ["en"]

    async def stt_transcribe(self, audio: bytes, sample_rate: int):
        # A placeholder that ANSWERS, for the same reason as TTS above: a
        # recognizer that accepts audio and returns nothing is indistinguishable,
        # from the daemon's side, from a working plugin that heard silence.
        # TODO: run your recognizer over `audio` and return the transcript.
        return f"[{len(audio)} bytes at {sample_rate} Hz]"
"#,
        );
    }

    if capabilities.contains(&"actions") {
        imports.push("action");
        methods.push_str(
            r#"
    @action("$action.do_something.label")
    async def do_something(self, name: str = "world"):
        # An action is what the user drags into a command; its parameters render
        # as the fields of the editor. TODO: make it do something.
        #
        # DECLARED plane: the label above is a key and the DAEMON resolves it,
        # per request, in the user's language. It has to be in locales/en.json
        # or the command editor shows the key — `astra-plugin check` says so
        # first. `i18n.key("…")` builds the same string; a literal is clearer
        # in a decorator.
        #
        # RUNTIME plane, unlike that label: this process produces the string
        # below, so it resolves it — here, now, with a count no daemon knows.
        return self.i18n.tn("msg.done", 1, n="1")
"#,
        );
    }

    if capabilities.contains(&"triggers") {
        imports.push("trigger");
        methods.push_str(
            r#"
    @trigger("$trigger.something_happened.label")
    async def something_happened(self):
        # Declares the trigger; the label is a key the daemon resolves, like the
        # action's. To FIRE it, call
        # `await self.host.fire_trigger("something_happened", {})` from wherever
        # the event happens — and declare `fire_trigger` under `[permissions]`
        # in plugin.toml, or the daemon refuses the call.
        pass
"#,
        );
    }

    if capabilities.contains(&"ai_provider") {
        imports.push("AiChunk");
        methods.push_str(
            r#"
    async def ai_complete(self, request):
        # The whole of the `ai_provider` capability, and an async GENERATOR:
        # yield deltas as the model produces them. The SDK appends the
        # terminating `done` chunk when you return, so the last thing you yield
        # can be content.
        # TODO: stream from your model instead of echoing.
        last = request.messages[-1].content if request.messages else ""
        yield AiChunk.delta(f"You said: {last}")
"#,
        );
    }

    let ui = capabilities.contains(&"ui_contributions") || capabilities.contains(&"dom_access");
    if ui {
        imports.push("ui_call");
        methods.push_str(
            r#"
    @ui_call
    async def ping(self):
        # Reachable from the iframe as `astra.call("ping", {})`. Push data the
        # other way with `await self.host.push_to_ui(...)`, which needs the
        # `push_to_ui` permission in plugin.toml.
        return {"ok": True}
"#,
        );
    }

    if capabilities.contains(&"event_handlers") {
        methods.push_str(
            r#"
    def subscribed_events(self):
        # Daemon events, gated on the `subscribe_events` permission — declare it
        # in plugin.toml or the daemon refuses the subscription. Chat events do
        # NOT arrive here; override `on_conversation_event` for those.
        return ["state_changed"]

    async def on_event(self, event_type: str, payload: dict):
        await self.log_debug(f"event: {event_type}")
"#,
        );
    }

    if capabilities.contains(&"client") {
        methods.push_str(
            r#"
    def is_client(self) -> bool:
        # Asks the daemon for a client session, so `on_daemon_client_ready` gets
        # a DaemonClient and this plugin can drive chat, voice and commands
        # rather than only answer.
        return True

    async def on_daemon_client_ready(self, client):
        self.daemon = client
        await self.log_info("daemon client ready")
"#,
        );
    }

    let import_list = imports.join(", ");

    // The UI contributions themselves are declared with a CLASS decorator —
    // `@ui_page` registers, it does not return something to be plumbed. That is
    // the whole point of §5.8's change, so the scaffold has to show it.
    let class_decorator = if ui {
        "@ui_page(\"main\", \"My Plugin\", \"web/index.html\")\n"
    } else {
        ""
    };
    let ui_page_import = if ui { ", ui_page" } else { "" };

    format!(
        r#""""{class_name} — Astra plugin."""

from astra_plugin_sdk import {import_list}{ui_page_import}


{class_decorator}class {class_name}(Plugin):
    """Astra plugin: {name}."""
{methods}

if __name__ == "__main__":
    {class_name}().run()
"#
    )
}

/// The generated test suite, written to `tests/test_plugin.py`.
///
/// One passing test that is not a smoke test: it drives the plugin through the
/// SDK's level-1 `Harness`, which runs the real capability servicer — so tool
/// registration, the JSON round trip and the error taxonomy are all on the path.
/// Blocking calls, plain `def test_…`, no pytest-asyncio.
pub fn generate_test_py(name: &str, capabilities: &[&str]) -> String {
    let class_name = class_name(name);

    let body = if capabilities.contains(&"tools") {
        format!(
            r#"
def test_hello_greets_and_its_schema_matches_its_handler():
    with Harness({class_name}()) as h:
        assert h.tool_names() == ["hello"]

        # The schema the model is shown really declares the parameters the
        # handler takes — `@tool` builds it from the signature, and this is what
        # catches the day the two stop agreeing.
        h.assert_schema_accepts("hello", "name", "excited")
        assert h.schema("hello")["required"] == ["name"]

        result = h.call_tool("hello", name="Ada", excited=True)
        assert result.success, result.code
        assert result.json == "Hello, Ada!"
"#
        )
    } else {
        format!(
            r#"
def test_the_plugin_starts_and_answers_a_health_check():
    with Harness({class_name}()) as h:
        healthy, _status = h.health()
        assert healthy
"#
        )
    };

    format!(
        r#""""Tests for {class_name}.

Run: `pytest`.

This is level 1: in process, no daemon, no socket, fast enough to run on every
save. It still goes through the real gRPC servicer, so a tool that is declared
but not routed fails here. When you want the other level — a real handshake, a
real session token, real protobuf encoding — reach for `WireHarness` from the
same module.
"""

import sys
from pathlib import Path

# The daemon puts the bundle root on `sys.path` before importing `src.plugin`;
# do the same so `pytest` from the project root finds it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from astra_plugin_sdk.testing import Harness, fuzz_configs  # noqa: E402

from src.plugin import {class_name}  # noqa: E402
{body}

def test_no_config_the_daemon_can_deliver_crashes_this_plugin():
    # The daemon delivers config it did not author: the user's typing, and an
    # older version of this plugin's own schema. `{{}}` — a fresh install — is
    # the first payload every plugin ever sees. None of it may throw.
    with Harness({class_name}()) as h:
        for payload in fuzz_configs():
            h.set_config(payload)
"#
    )
}

pub fn generate_requirements() -> String {
    // Pinned to the minor that carries the authenticated `HostClientBootstrap`
    // flow. A bare name resolves to whatever PyPI has, including 0.4.x, whose
    // host stubs send no `x-session-token` and get `unauthenticated` on every
    // call — a scaffold that cannot work.
    r#"astra-plugin-sdk>=0.6,<0.7
grpcio>=1.60.0
grpcio-tools>=1.60.0
protobuf>=4.25.0
"#
    .into()
}

pub fn generate_pyproject(name: &str) -> String {
    let pkg_name = name.replace('-', "_");
    format!(
        r#"[project]
name = "{pkg_name}"
version = "0.1.0"
description = "An Astra plugin"
requires-python = ">=3.10"
dependencies = [
    "astra-plugin-sdk>=0.6,<0.7",
    "grpcio>=1.60.0",
    "protobuf>=4.25.0",
]

[project.optional-dependencies]
# `pip install -e ".[dev]"`, then `pytest`. The harness itself ships in the SDK,
# so this extra adds the runner and nothing else.
dev = ["pytest>=7.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
"#
    )
}

//! TypeScript plugin project templates.
//!
//! The scaffold is the object form (`plugin({...})` with the `s` schema
//! builder), because the shape a new author copies is the shape they keep. Two
//! properties matter and both are load-bearing:
//!
//! * **The tool's parameters are declared once.** `s.object({...})` emits the
//!   JSON Schema the model reads AND types the handler's argument, so a
//!   scaffold cannot teach the `String(args.x ?? "")` habit that lets a schema
//!   and its handler drift apart.
//! * **`app` is exported and only runs as the entrypoint.** That is what makes
//!   the generated test possible: it drives the plugin through the SDK's
//!   harness without starting a gRPC server.

/// `PascalCase` from a hyphenated plugin id — used for the display name only.
fn title_case(name: &str) -> String {
    name.split('-')
        .map(|w| {
            let mut c = w.chars();
            match c.next() {
                None => String::new(),
                Some(f) => f.to_uppercase().to_string() + c.as_str(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

pub fn generate_index_ts(name: &str, capabilities: &[&str]) -> String {
    let title = title_case(name);
    let mut sections = String::new();

    if capabilities.contains(&"tools") {
        sections.push_str(
            r#"
  tools: {
    hello: tool({
      description: "Greet someone by name.",
      // Declared once: this is the JSON Schema the model is shown AND the type
      // of `run`'s first argument. The SDK validates the model's arguments
      // against it before your code runs, so `name` really is a string.
      input: s.object({
        name: s.string({ description: "Who to greet" }),
        excited: s.boolean({ description: "Add an exclamation mark" }).optional(),
      }),
      run: ({ name, excited }) => `Hello, ${name}${excited ? "!" : "."}`,
    }),
  },
"#,
        );
    }

    if capabilities.contains(&"tts") {
        sections.push_str(
            r#"
  tts: {
    voices: [{ id: "default", name: "Default Voice", language: "en", gender: "neutral" }],
    synthesize: ({ text }) => {
      // A placeholder that ANSWERS: 200 ms of 16 kHz silence. Throwing here
      // instead would make a freshly scaffolded plugin fail `astra-plugin test`
      // — the project's own conformance suite — before its author had written
      // a line, which teaches exactly the wrong thing about a red run.
      // TODO: synthesize `text` and put the PCM in `data`.
      return {
        data: Buffer.alloc(3200 * 2),
        format: "pcm_s16le",
        sampleRate: 16000,
        durationMs: 200,
      };
    },
  },
"#,
        );
    }

    // `--template stt-streaming` asks for the streaming hook instead of the
    // unary one. Same capability — there is only one STT capability — but the
    // hook an author starts from decides whether their plugin can ever emit a
    // partial result, and bolting `transcribeStream` onto a finished unary
    // implementation is the retrofit people get subtly wrong.
    if capabilities.contains(&crate::commands::create::STREAMING_MARKER) {
        sections.push_str(
            r#"
  stt: {
    languages: ["en"],
    // Streaming: implementing this takes precedence over `transcribe`. Yield
    // `{ isFinal: false }` results as you recognize them so the user sees text
    // while still speaking, and one final result before returning.
    //
    // Back-pressure is real: the SDK buffers a bounded number of chunks — the
    // same bound the daemon uses — and the daemon dumps its whole wake-word
    // pre-roll in at once. Read in a loop; never await anything slow between
    // reads.
    // TODO: feed each chunk to your recognizer.
    async *transcribeStream(audio) {
      let chunks = 0;
      for await (const _chunk of audio) chunks++;
      yield { text: `[${chunks} chunks]`, isFinal: true };
    },
  },
"#,
        );
    } else if capabilities.contains(&"stt") {
        sections.push_str(
            r#"
  stt: {
    languages: ["en"],
    // One-shot: the SDK buffers the whole utterance and calls this once.
    // Implement `transcribeStream` instead for partial results as audio arrives.
    transcribe: (audio, { sampleRate }) => {
      // A placeholder that ANSWERS, for the same reason as TTS: a recognizer
      // that accepts an utterance and produces NOTHING is, from the daemon's
      // side, a successful call — which is how a broken STT plugin actually
      // presents (mic works, waveform moves, no text ever).
      // TODO: recognize `audio` (16-bit little-endian PCM at `sampleRate`).
      return { text: `[${audio.length} bytes at ${sampleRate} Hz]`, isFinal: true };
    },
  },
"#,
        );
    }

    if capabilities.contains(&"actions") {
        sections.push_str(
            r#"
  actions: {
    say_something: action({
      label: "Say Something",
      // `fields` is what the command editor renders; `params` types the
      // handler. Keep the two describing the same values.
      fields: [Field.text("message", "Message", { placeholder: "Hello" })],
      params: s.object({ message: s.string() }),
      // RUNTIME plane, unlike the label above: this process produces the
      // string, so it resolves it — now, in the user's language, with a count
      // no daemon can know. The keys are in locales/en.json.
      run: ({ message }, ctx) => `${ctx.i18n.tn("msg.done", 1, { n: "1" })}: ${message}`,
    }),
  },
"#,
        );
    }

    if capabilities.contains(&"triggers") {
        sections.push_str(
            r#"
  triggers: {
    // Fire it from anywhere with `ctx.fireTrigger("something_happened", {...})`.
    something_happened: {
      label: "Something Happened",
      fields: [],
    },
  },
"#,
        );
    }

    if capabilities.contains(&"ai_provider") {
        sections.push_str(
            r#"
  ai: {
    // The whole of the `ai_provider` capability. An async generator: yield text
    // deltas as the model produces them; the SDK appends the terminating `done`
    // chunk when you return, so the last thing you yield can be content.
    // TODO: stream from your model instead.
    async *complete(req) {
      yield `You said: ${req.messages.at(-1)?.content ?? ""}`;
    },
  },
"#,
        );
    }

    if capabilities.contains(&"ui_contributions") || capabilities.contains(&"dom_access") {
        sections.push_str(
            r#"
  ui: {
    // The iframes this plugin puts in Astra's window. `url` is served from the
    // plugin's own bundle.
    contributions: [UiContrib.page("main", "My Plugin", "web/index.html")],
    // Reachable from that iframe as `astra.call("ping", {})`. Push data the
    // other way with `ctx.pushToUi(...)`.
    onCall: {
      ping: () => ({ ok: true }),
    },
  },
"#,
        );
    }

    if capabilities.contains(&"event_handlers") {
        sections.push_str(
            r#"
  events: {
    // Daemon events to subscribe to — gated on the `subscribe_events`
    // permission, so declare it in plugin.toml or the daemon refuses.
    // Chat events do NOT arrive here; those are `onConversation`, below.
    subscribe: ["state_changed"],
    on: (eventType, _payload, ctx) => {
      void ctx.log("debug", `event: ${eventType}`);
    },
  },
"#,
        );
    }

    if capabilities.contains(&"client") {
        sections.push_str(
            r#"
  // Declaring `client` is what asks the daemon for a client session, so this
  // plugin can drive chat, voice and commands rather than only answer.
  client: {
    onReady: (_daemon, ctx) => {
      void ctx.info("daemon client ready");
    },
  },
"#,
        );
    }

    if sections.is_empty() {
        sections.push_str(
            r#"
  // Nothing declared yet. Add `tools`, `actions`, `triggers`, `tts`, `stt`,
  // `ai` or `ui` — see https://github.com/mihailinl/AstraPlugins.
"#,
        );
    }

    let mut imports = vec!["plugin", "s"];
    if capabilities.contains(&"tools") {
        imports.push("tool");
    }
    if capabilities.contains(&"actions") {
        imports.push("action");
        imports.push("Field");
    }
    if capabilities.contains(&"ui_contributions") || capabilities.contains(&"dom_access") {
        imports.push("UiContrib");
    }
    let import_list = imports.join(", ");

    format!(
        r#"/**
 * {title} — an Astra plugin.
 *
 * The plugin is a VALUE, exported from this module, and it starts only when
 * this file is the process entrypoint. That is what lets `test/plugin.test.mjs`
 * drive it in-process, with no daemon and no socket.
 */

import {{ {import_list} }} from "astra-plugin-sdk";

export const app = plugin({{{sections}}});

// `astra-plugin build` bundles this to CommonJS, so `require.main` is the
// honest "am I the entrypoint" test. Importing this module — as the test does —
// does not start a server.
if (require.main === module) app.run();
"#
    )
}

/// The generated test suite. One passing test, and it is not a smoke test:
/// it asserts the tool's schema and its handler agree, which is the property
/// the object form exists to hold.
///
/// Written to `test/plugin.test.mjs` by
/// `commands/create.rs::generate_typescript_project`. The scaffold's `test`
/// script globs that directory, so this file is what stops `npm test` from
/// passing with zero tests in it.
pub fn generate_test_ts(name: &str, capabilities: &[&str]) -> String {
    let title = title_case(name);
    let tool_block = if capabilities.contains(&"tools") {
        r#"
test("hello greets, and its schema matches its handler", async () => {
  const h = await Harness.create(app).start();

  assert.deepEqual(await h.toolNames(), ["hello"]);

  // The schema the model is shown really is an object with the keys the
  // handler destructures, and `excited` really is optional in both.
  await h.assertSchemaAccepts("hello", { name: "Ada" });
  await h.assertSchemaAccepts("hello", { name: "Ada", excited: true });
  await h.assertSchemaRejects("hello", { name: 42 });

  const result = await h.callTool("hello", { name: "Ada", excited: true });
  assert.equal(result.success, true);
  assert.equal(result.result, "Hello, Ada!");

  // An argument the schema forbids never reaches the handler; it comes back as
  // an in-band BAD_ARGUMENTS the assistant can read and correct.
  const bad = await h.callTool("hello", {});
  assert.equal(bad.success, false);
  assert.match(bad.error, /BAD_ARGUMENTS/);
});
"#
    } else {
        r#"
test("the plugin starts, and answers a health check", async () => {
  const h = await Harness.create(app).start();
  assert.equal((await h.healthCheck()).healthy, true);
});
"#
    };

    format!(
        r#"/**
 * Tests for {title}.
 *
 * `pretest` bundles `src/index.ts` with the SDK left EXTERNAL, so the plugin
 * under test and the harness testing it share one copy of the SDK.
 *
 * Run: `npm test`.
 *
 * This is level 1: in process, no daemon, no socket, fast enough to run on
 * every save. When you want the other level — a real gRPC handshake, a real
 * session token, real protobuf encoding — reach for `MockDaemon` from the same
 * module and see `examples/json-tools/test/plugin.test.mjs`.
 */

import assert from "node:assert/strict";
import {{ createRequire }} from "node:module";
import {{ test }} from "node:test";

const require = createRequire(import.meta.url);

const {{ app }} = require("../dist/plugin.cjs");
const {{ Harness }} = require("astra-plugin-sdk/testing");
{tool_block}
test("no config the daemon can deliver crashes this plugin", async () => {{
  // The daemon delivers config it did not author: the user's typing, and an
  // older version of this plugin's own schema. None of it may throw.
  const h = await Harness.create(app).start();
  assert.deepEqual(await h.fuzzConfig(), []);
}});
"#
    )
}

pub fn generate_package_json(name: &str) -> String {
    // The published npm name is unscoped: `astra-plugin-sdk-ts/package.json`
    // declares `"name": "astra-plugin-sdk"` and the release train in
    // `.github/workflows/release-sdks.yml` runs a plain `npm publish` from that
    // directory. `@astra/plugin-sdk` was scaffolded here for a scope that was
    // never registered, so every generated TypeScript project 404'd on
    // `npm install`. The wrong name is spelled out once, here, because a reader
    // who finds it in an old project needs to recognise it.
    //
    // `pretest` bundles the plugin with the SDK EXTERNAL so the test and the
    // code under test share one copy; `build` bundles everything, because what
    // ships is one file and the daemon installs no node_modules.
    format!(
        r#"{{
  "name": "{name}",
  "version": "0.1.0",
  "description": "An Astra plugin",
  "main": "dist/index.js",
  "scripts": {{
    "build": "bun install --frozen-lockfile && esbuild src/index.ts --bundle --platform=node --format=cjs --outfile=dist/index.js",
    "pretest": "esbuild src/index.ts --bundle --platform=node --format=cjs --external:astra-plugin-sdk --outfile=dist/plugin.cjs",
    "test": "node --test test/*.test.mjs",
    "typecheck": "tsc --noEmit",
    "dev": "tsx src/index.ts"
  }},
  "engines": {{
    "node": ">=20"
  }},
  "dependencies": {{
    "astra-plugin-sdk": "^0.6.0",
    "@grpc/grpc-js": "^1.10.0",
    "@grpc/proto-loader": "^0.7.0"
  }},
  "devDependencies": {{
    "@types/node": "^20.0.0",
    "esbuild": "^0.20.0",
    "tsx": "^4.0.0",
    "typescript": "^5.4.0"
  }}
}}
"#
    )
}

pub fn generate_tsconfig() -> String {
    // `moduleResolution: bundler` is what reads the SDK's `exports` map, which
    // is how `astra-plugin-sdk/testing` resolves at all. `types: ["node"]` is
    // required by the `require.main` guard in the generated entrypoint.
    r#"{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "esModuleInterop": true,
    "strict": true,
    "outDir": "dist",
    "rootDir": "src",
    "declaration": true,
    "types": ["node"]
  },
  "include": ["src"]
}
"#
    .into()
}

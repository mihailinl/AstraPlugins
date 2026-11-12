> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../en/image-provider-plugins.md) maßgeblich.


# Bild-Provider-Plugins

Ein Bild-Provider-Plugin deklariert `image_provider = true` im Abschnitt
`[capabilities]` seiner `plugin.toml`. Astra fragt es dann nach den Bildern,
die das Werkzeug `generate_image` des Assistenten zeichnet. **Noch fragt kein
Astra-Release danach** (2026-11-13): Die Daemon-Seite, Astra `21790d761`,
steckt hinter dem Build-Feature `plugin-provider-slots`, und jedes andere
Astra ruft den Hook nie auf.

Astra fragt das Plugin in zwei Fällen:

- **Solange es der KI-Provider des Chats ist.** Ein Plugin, das sowohl
  `ai_provider` als auch `image_provider` deklariert und der Provider ist, mit
  dem die Person gerade chattet, wird ZUERST gefragt. Der eigene Bild-Provider
  der Person (**KI → Bildgenerierung**) ist der Fallback; ihre Einstellungen
  werden nie umgeschrieben.
- **Wenn die Person es als Bild-Provider gewählt hat.** Die Wahl wird als
  `plugin__<plugin id>` gespeichert, mit Bindestrichen in Unterstriche
  verwandelt — `plugin__my_painter` —, wie bei den Provider-IDs für TTS und
  STT und anders als bei denen der Websuche. Die Auswahl auf der KI-Seite
  listet nur KI-Provider, sodass ein Plugin, das zeichnet und nicht zugleich
  KI-Provider ist, dort noch nicht gewählt werden kann.

Die Capability ist ein Pflicht-Hook, `ImageGenerate` — ein Prompt hinein, ein
Bild oder eine Ablehnung hinaus — und ein optionaler Hook, `ImageGetModels`.

## Was Astra übernimmt, damit das Plugin es nicht tun muss

- **Die Kette.** Wenn dein Plugin ablehnt oder scheitert, versucht Astra
  selbständig den nächsten Provider — es sei denn, der Prompt selbst wurde
  abgelehnt. Dein Plugin ruft nie einen anderen Bilddienst auf.
- **Das Zählen.** Astra verlangt EIN Bild pro Aufruf. Eine Person, die vier
  verlangt hat, kostet vier Aufrufe, und Astra hört beim ersten auf, der
  fehlschlägt.
- **Speichern und Anzeigen.** Astra speichert das Bild, zeigt es im Chat an
  und sagt dem Modell, wo es liegt. Gib die Bytes zurück; nie eine URL oder
  einen Pfad.
- **Die Prüfung.** Das Bild wird an seinen eigenen Bytes geprüft: PNG, JPEG
  oder WEBP. Alles andere wird abgelehnt, wie auch immer es beschriftet ist,
  und ein leeres ebenso.
- **Die Worte.** `error_message` und `caption` erreichen das Modell als eine
  Zeile fremden Textes, bereinigt.

## Einen Provider anlegen

<!-- doctest: cli -->
```bash
astra-plugin new my-painter --lang python --template blank --capabilities image_provider --output ./my-painter
```

`--lang` kann auch `rust` oder `typescript` sein. Es gibt kein Bild-Template:
Die Capability kommt über `--capabilities`, und der Hook des Scaffolds
antwortet `not_configured`, bis du ihn implementierst. `astra-plugin test`
ruft `ImageGenerate` mit einem echten Prompt und `ImageGetModels` auf; eine
Ablehnung besteht den Test, weil sie eine Antwort ist.

`[capabilities]` ist eine geschlossene Menge, sodass ein Astra, das
`image_provider` nicht kennt, das ganze Manifest ablehnt. Noch kennt es kein
Release, also gibt es keine `min_astra_version` zu nennen; füge eine hinzu,
wenn ein Release die Capability ausliefert. Bewahre den API-Schlüssel des
Providers im eigenen `[config]`-Schema des Plugins auf, wo die Person ihn auf
der Plugins-Seite setzt:

<!-- doctest: toml-manifest -->
```toml
[plugin]
id = "my-painter"
name = "My Painter"
version = "0.1.0"
description = "Pictures through Example Images"
author = "You"
license = "MIT"

[entry]
command = "python"
args = ["-u", "-m", "src.plugin"]
runtimes = ["python"]

[capabilities]
image_provider = true

[config]
schema = """
{
  "type": "object",
  "properties": {
    "api_key": {
      "type": "string",
      "format": "password",
      "default": "",
      "title": "API key",
      "description": "Your Example Images key"
    }
  }
}
"""
```

## Die Anfrage

| Feld | Wert |
|---|---|
| `prompt` | Was zu zeichnen ist, so wie das Modell es geschrieben hat |
| `aspect_ratio` | `""` für den eigenen Standard des Modells, oder eines von `1:1`, `16:9`, `9:16`, `4:3`, `3:4`. Zeichne in deinem Standard, wenn deine API es nicht ausdrücken kann |
| `model` | Das Modell, das die Person gewählt hat — eine ID aus deiner `ImageGetModels`-Liste, oder eingetippt — und `""` für deinen Standard |
| `input_images` | Die Bilder, die die Person zum Bearbeiten oder als Vorlage angehängt hat, die Bytes unverändert. Leer, es sei denn, das Modell ist eines, das deine Liste mit `accepts_input_images` markiert |

## Die Antwort

Genau ein Bild — PNG-, JPEG- oder WEBP-Bytes, mit jedem Text, den das Modell
daneben geschrieben hat, als `caption` — oder eine Ablehnung. **Eine Ablehnung
ist eine Antwort, kein Fehler.** Gib sie zurück; raise oder throw sie nicht:

| `error_code` | Wann | Was Astra tut |
|---|---|---|
| `quota` | Das Kontingent des Kontos ist aufgebraucht | Versucht den nächsten Provider; sagt dem Modell in deinen Worten, dass das Kontingent aufgebraucht ist |
| `rate_limited` | Gerade zu viele Bilder; setze `retry_after_secs`, wenn die API sagt, wie lange | Versucht den nächsten Provider; sagt dem Modell, es solle warten |
| `not_configured` | Eine Einstellung, die die Person vornehmen muss, fehlt — meist der Schlüssel | Versucht den nächsten Provider; sagt dem Modell, dass der Provider nicht eingerichtet ist |
| `unavailable` | Alles andere: der Dienst ist down, das Netzwerk hat versagt, die Antwort war unlesbar | Versucht den nächsten Provider |
| `refused` | Der Prompt selbst wurde abgelehnt — ein Sicherheitsfilter, eine weiche Ablehnung | Versucht nichts anderes: Ein anderer Provider bekäme denselben Prompt |

`error_message` ist kurz und auf einfachem Englisch: Das Modell liest es. Ein
`error_code` außerhalb dieser fünf wird als `unavailable` gelesen. Eine
Antwort ohne Bild und ohne Code wird als abgelehnter Prompt gelesen, sodass
nichts anderes versucht wird — jedes SDK weigert sich, eine solche zu senden.
Astra wartet `retry_after_secs` für ein Bild noch nicht ab; das Feld steht
auf dem Draht für den Tag, an dem es das tut.

Was KEINE Antwort ist: eine ausgelöste Exception, ein geworfener Fehler oder
ein Rust-`Err` erreicht Astra als fehlgeschlagener Aufruf, den es als
Scheitern dieses Plugins liest, und es geht zum nächsten Provider weiter —
eine Ablehnung, die du meintest, aber stattdessen ausgelöst hast, verliert
also ihren Code. Ein Plugin, das `image_provider` deklariert und den Hook
nicht implementiert, antwortet `UNIMPLEMENTED`, was Astra als nicht
eingerichteten Provider meldet.

Astra wartet auf ein Bild höchstens das Kleinere von
`plugin.call_timeout_secs` (120 Sekunden, wenn nicht gesetzt) und seiner
eigenen Obergrenze: 150 Sekunden, oder 55, solange der Chat auf Astra AI
läuft, dessen Server bei 60 aufhört, auf ein Werkzeug zu warten. Gib der
Anfrage an deinen Dienst ein Timeout innerhalb dessen, und antworte
`unavailable`, wenn es auslöst.

## Modelle, und ein Bild bearbeiten

`ImageGetModels` ist optional. Es listet die Modelle, die die Auswahl anbietet
— eine `id`, einen `name` und ob das Modell Bilder zum Bearbeiten annimmt
(`accepts_input_images`) — und das `default_model`, das verwendet wird, wenn
die Person keines nennt (`""` = das erste). Astra verwirft ein Modell, dessen
ID leer ist, länger als 200 Zeichen ist oder ein Steuerzeichen enthält, und
ignoriert ein `default_model`, das nicht in der Liste steht.

So entscheidet Astra auch, ob es ein Bild sendet. Wenn die Person Bilder
angehängt und um eine Bearbeitung gebeten hat, fragt Astra zuerst
`ImageGetModels`, nimmt das Modell, das die Person gewählt hat (sonst
`default_model`, sonst das erste), und sendet ALLE Bilder in `input_images`
nur dann, wenn dieses Modell mit `accepts_input_images` gelistet ist.
Andernfalls sagt es dem Modell, dass dieser Provider nicht bearbeiten kann,
und versucht den nächsten. Ein Plugin ohne Liste bekommt nie ein Bild zum
Bearbeiten.

## Rust

`image_generate` auf `PluginCapability` (oder als `#[hook]` innerhalb von
`#[astra::plugin]`) nimmt eine `ImageRequest` und gibt
`anyhow::Result<ImageResponse>` zurück. `ImageResponse::drawn(bytes)` liest
den Typ des Bildes aus seinen Bytes; `.with_caption(text)` fügt die
Bildunterschrift hinzu. `ImageResponse::refuse(ImageErrorCode::…, message)`
baut eine Ablehnung, und `.with_retry_after(secs)` kommt auf eine
`RateLimited`-Ablehnung. `image_models` gibt `(models, default_model)`
zurück; `ImageModelInfo::new(id, name).accepts_input_images()` markiert ein
Modell, das bearbeitet. Die Platzhalterfunktion unten ist, wo dein
HTTP-Client hingehört — das SDK liefert keinen mit.

<!-- doctest: rust-plugin test=1 -->
```rust
use astra_plugin_sdk::prelude::*;
use std::sync::Mutex;

/// Settings. `#[astra::config]` fills a missing field from `Default`, because
/// a fresh install's first config payload is `{}`.
#[astra::config]
#[derive(Default)]
struct Settings {
    api_key: String,
}

#[derive(Default)]
struct MyPainter {
    settings: Mutex<Settings>,
}

/// What your provider's API can say. Each variant maps onto one refusal code.
enum ApiError {
    Spent,
    TooFast { retry_after: u32 },
    Declined(String),
    Down(String),
}

/// Stands in for the HTTP call to your provider, so this sample runs. A real
/// one returns the bytes of the picture your API drew.
fn call_api(key: &str, req: &ImageRequest) -> Result<Vec<u8>, ApiError> {
    match key {
        "spent" => Err(ApiError::Spent),
        "fast" => Err(ApiError::TooFast { retry_after: 30 }),
        "down" => Err(ApiError::Down("HTTP 503".into())),
        _ if req.prompt.contains("forbidden") => {
            Err(ApiError::Declined("the safety filter declined the prompt".into()))
        }
        _ => Ok(vec![0x89, b'P', b'N', b'G', 0x0d, 0x0a, 0x1a, 0x0a]),
    }
}

#[astra::plugin]
impl MyPainter {
    /// Called on start and on every settings change.
    #[hook]
    async fn on_config(&self, _ctx: &PluginContext, cfg: Settings) {
        *self.settings.lock().unwrap() = cfg;
    }

    /// Draw one picture for the assistant's `generate_image` tool.
    #[hook]
    async fn image_generate(
        &self,
        _ctx: &PluginContext,
        req: ImageRequest,
    ) -> anyhow::Result<ImageResponse> {
        let key = self.settings.lock().unwrap().api_key.clone();
        if key.is_empty() {
            return Ok(ImageResponse::refuse(
                ImageErrorCode::NotConfigured,
                "set an API key in the plugin's settings",
            ));
        }
        Ok(match call_api(&key, &req) {
            Ok(picture) => ImageResponse::drawn(picture),
            Err(ApiError::Spent) => {
                ImageResponse::refuse(ImageErrorCode::Quota, "the plan's allowance is spent")
            }
            Err(ApiError::TooFast { retry_after }) => {
                ImageResponse::refuse(ImageErrorCode::RateLimited, "too many pictures")
                    .with_retry_after(retry_after)
            }
            Err(ApiError::Declined(why)) => ImageResponse::refuse(ImageErrorCode::Refused, why),
            Err(ApiError::Down(why)) => ImageResponse::refuse(
                ImageErrorCode::Unavailable,
                format!("the provider is down: {why}"),
            ),
        })
    }

    /// The models the picker offers. `edit-1` takes pictures to edit.
    #[hook]
    async fn image_models(
        &self,
        _ctx: &PluginContext,
    ) -> anyhow::Result<(Vec<ImageModelInfo>, String)> {
        Ok((
            vec![
                ImageModelInfo::new("draw-1", "Draw 1"),
                ImageModelInfo::new("edit-1", "Edit 1").accepts_input_images(),
            ],
            "draw-1".into(),
        ))
    }
}

astra::main!(MyPainter::default());

#[cfg(test)]
mod tests {
    use super::*;
    use astra_plugin_sdk::testing::Harness;

    #[tokio::test]
    async fn no_key_is_a_refusal_not_an_error() {
        let h = Harness::new(MyPainter::default()).start().await.unwrap();
        let answer = h.image_generate(ImageRequest::new("a fox")).await.unwrap();
        assert!(matches!(
            answer,
            ImageResponse::Refused { code: ImageErrorCode::NotConfigured, .. }
        ));
    }

    #[tokio::test]
    async fn a_key_gets_one_png() {
        let h = Harness::new(MyPainter::default())
            .with_config(json!({ "api_key": "k" }))
            .start()
            .await
            .unwrap();
        let ImageResponse::Drawn { mime_type, .. } =
            h.image_generate(ImageRequest::new("a fox")).await.unwrap()
        else {
            panic!("expected a picture");
        };
        assert_eq!(mime_type, "image/png");
    }
}
```

## Python

Überschreibe `image_generate(self, request)` auf `Plugin`. Es erhält eine
`ImageRequest` und gibt eine `ImageResponse` zurück — oder die Bytes des
Bildes, was bedeutet, dass es gezeichnet wurde.
`ImageResponse.drawn(data, caption=…)` liest den Typ aus den Bytes;
`ImageResponse.refuse(code, message, retry_after_secs=0)` prüft den Code,
sodass ein Tippfehler in deinem eigenen Test scheitert.
`image_get_models(self)` gibt eine `ImageModelList` zurück, oder ein Tupel
`(models, default_model)`. Blockierendes I/O gehört auf einen Thread
(`asyncio.to_thread`): Der Hook teilt seinen Event-Loop mit jedem anderen
Hook, den das Plugin bedient.

<!-- doctest: python-plugin -->
```python
"""MyPainter — an image provider plugin."""

import asyncio
import base64
import json
import urllib.error
import urllib.request

from astra_plugin_sdk import (
    ImageErrorCode,
    ImageModelInfo,
    ImageModelList,
    ImageResponse,
    Plugin,
)

API = "https://api.example.com/images"


def call_api(key, prompt, aspect_ratio, model, timeout=90):
    body = json.dumps({"prompt": prompt, "aspect_ratio": aspect_ratio or "1:1", "model": model})
    req = urllib.request.Request(
        API,
        data=body.encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return base64.b64decode(json.load(response)["image_base64"])


class MyPainter(Plugin):
    """Pictures through Example Images."""

    async def image_generate(self, request):
        key = self.config.get("api_key", "")
        if not key:
            return ImageResponse.refuse(
                ImageErrorCode.NOT_CONFIGURED, "set an API key in the plugin's settings"
            )
        try:
            picture = await asyncio.to_thread(
                call_api, key, request.prompt, request.aspect_ratio, request.model
            )
        except urllib.error.HTTPError as e:
            if e.code == 402:
                return ImageResponse.refuse(ImageErrorCode.QUOTA, "the plan's allowance is spent")
            if e.code == 429:
                after = e.headers.get("Retry-After", "")
                retry = int(after) if after.isdigit() else 0  # an HTTP date says nothing usable here
                return ImageResponse.refuse(
                    ImageErrorCode.RATE_LIMITED, "too many pictures", retry_after_secs=retry
                )
            if e.code == 400 and "content_policy" in e.read().decode("utf-8", "replace"):
                # Only a refusal OF THE PROMPT is `refused`: Astra then asks no other provider.
                return ImageResponse.refuse(ImageErrorCode.REFUSED, "the prompt was declined")
            if e.code in (401, 403):
                return ImageResponse.refuse(ImageErrorCode.NOT_CONFIGURED, "the API key was refused")
            return ImageResponse.refuse(ImageErrorCode.UNAVAILABLE, f"HTTP {e.code}")
        except OSError as e:
            return ImageResponse.refuse(ImageErrorCode.UNAVAILABLE, f"network: {e}")
        return ImageResponse.drawn(picture)

    async def image_get_models(self):
        return ImageModelList(
            models=[
                ImageModelInfo("draw-1", "Draw 1"),
                ImageModelInfo("edit-1", "Edit 1", accepts_input_images=True),
            ],
            default_model="draw-1",
        )


def test_no_key_is_a_refusal_not_an_error():
    from astra_plugin_sdk.testing import Harness

    with Harness(MyPainter()) as h:
        answer = h.image_generate("a fox")
        models = h.image_models()
    assert answer.error_code == ImageErrorCode.NOT_CONFIGURED
    assert answer.data == b""
    assert [m.id for m in models.models if m.accepts_input_images] == ["edit-1"]


if __name__ == "__main__":
    MyPainter().run()
```

## TypeScript

Gib `plugin({...})` einen Abschnitt `image` — `generate(req, ctx)` und,
optional, `models` (eine Liste, oder `(ctx) => list`) — oder überschreibe
`imageGenerate(req)` und `imageGetModels()` auf einer `Plugin`-Subklasse.
Baue die Antwort mit `ImageGeneration.drawn(bytes, { caption })`, das den Typ
aus den Bytes liest, oder mit `ImageGeneration.refuse(code, message,
retryAfterSecs)`; `generate` darf auch die Bytes zurückgeben.

<!-- doctest: ts-plugin -->
```typescript
import { plugin, ImageGeneration } from "astra-plugin-sdk";

export const app = plugin({
  image: {
    async generate(req, ctx) {
      const key = ctx.configValue<string>("api_key", "");
      if (!key) return ImageGeneration.refuse("not_configured", "set an API key in the plugin's settings");

      let res: Response;
      try {
        res = await fetch("https://api.example.com/images", {
          method: "POST",
          headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: req.prompt, aspect_ratio: req.aspectRatio || "1:1", model: req.model }),
          signal: AbortSignal.timeout(90_000),
        });
      } catch (e) {
        return ImageGeneration.refuse("unavailable", `network: ${String(e)}`);
      }
      if (res.status === 402) return ImageGeneration.refuse("quota", "the plan's allowance is spent");
      if (res.status === 429) {
        return ImageGeneration.refuse("rate_limited", "too many pictures", Number.parseInt(res.headers.get("retry-after") ?? "", 10) || 0);
      }
      if (res.status === 400 && (await res.clone().text()).includes("content_policy")) {
        // Only a refusal OF THE PROMPT is `refused`: Astra then asks no other provider.
        return ImageGeneration.refuse("refused", "the prompt was declined");
      }
      if (res.status === 401 || res.status === 403) return ImageGeneration.refuse("not_configured", "the API key was refused");
      if (!res.ok) return ImageGeneration.refuse("unavailable", `HTTP ${res.status}`);

      const body = (await res.json()) as { image_base64: string };
      return ImageGeneration.drawn(Buffer.from(body.image_base64, "base64"));
    },
    models: {
      models: [
        { id: "draw-1", name: "Draw 1" },
        { id: "edit-1", name: "Edit 1", acceptsInputImages: true },
      ],
      defaultModel: "draw-1",
    },
  },
});

if (require.main === module) app.run();
```

## Testen

Der Level-1-Harness jedes SDKs steuert die Hooks durch dieselbe
Draht-Projektion, die Astra sieht — ein Bild, oder die Ablehnung im Body:

| SDK | Aufruf | Gibt zurück |
|---|---|---|
| Rust | `running.image_generate(ImageRequest::new(..))`, `running.image_models()` | die `ImageResponse` des Hooks; sein `(models, default_model)` |
| Python | `harness.image_generate(prompt, aspect_ratio=…, model=…, input_images=…)`, `harness.image_models()` | eine vom Draht zurückgelesene `ImageResponse`; eine `ImageModelList` |
| TypeScript | `harness.imageGenerate(prompt, { aspectRatio, model, inputImages })`, `harness.imageGetModels()` | eine vom Draht zurückgelesene `ImageResponse`; eine `ImageModelList` |

Der Harness sendet `input_images`, was auch immer deine Liste sagt; zu
wählen, wer sie bekommt, ist Astras Teil. `astra-plugin test` verlangt ein
echtes Bild, mit 60 Sekunden Zeit dafür, und schlägt fehl bei allem, was
Astra falsch lesen oder ablehnen würde: ein `error_code` außerhalb der fünf,
eine Antwort ohne Bild und ohne Code, mehr als ein Bild, oder ein Bild, das
nach seinen Bytes nicht PNG, JPEG oder WEBP ist. Es liest die Modellliste so,
wie Astra sie zulässt. Lade dann mit `astra-plugin dev` seitwärts in ein
Astra, das mit `plugin-provider-slots` gebaut ist.

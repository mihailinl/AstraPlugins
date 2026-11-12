> **Traducción.** Esta es una traducción. Si hay alguna discrepancia, [`docs/en`](../en/image-provider-plugins.md) es la referencia autorizada.


# Plugins de proveedor de imágenes

Un plugin de proveedor de imágenes declara `image_provider = true` en la
sección `[capabilities]` de su `plugin.toml`. Astra le pide entonces las
imágenes que dibuja la herramienta `generate_image` del asistente.
**Ningún release de Astra lo pide todavía** (2026-11-13): el lado del
daemon, Astra `21790d761`, está detrás de la build feature
`plugin-provider-slots`, y cualquier otro Astra nunca llama al hook.

Astra pregunta al plugin en dos casos:

- **Mientras es el proveedor de IA del chat.** Un plugin que declara tanto
  `ai_provider` como `image_provider` y es el proveedor con el que la
  persona está chateando se consulta PRIMERO. El proveedor de imágenes
  propio de la persona (**IA → Generación de imágenes**) es el respaldo; sus
  ajustes nunca se reescriben.
- **Cuando la persona lo eligió como proveedor de imágenes.** La elección se
  guarda como `plugin__<plugin id>` con los guiones convertidos en guiones
  bajos — `plugin__my_painter` —, como en los ids de proveedor de TTS y STT,
  y a diferencia de los de la búsqueda web. El selector de la página de IA
  solo lista proveedores de IA, así que un plugin que dibuja y no es también
  proveedor de IA todavía no se puede elegir ahí.

La capability es un hook obligatorio, `ImageGenerate` — entra un prompt,
sale una imagen o un rechazo — y un hook opcional, `ImageGetModels`.

## Lo que hace Astra para que el plugin no tenga que hacerlo

- **La cadena.** Cuando tu plugin rechaza o falla, Astra prueba el siguiente
  proveedor por su cuenta — salvo que se haya rechazado el propio prompt.
  Tu plugin nunca llama a otro servicio de imágenes.
- **El recuento.** Astra pide UNA imagen por llamada. Una persona que pidió
  cuatro cuesta cuatro llamadas, y Astra se detiene en la primera que falla.
- **Guardar y mostrar.** Astra guarda la imagen, la muestra en el chat y le
  dice al modelo dónde está. Devuelve los bytes; nunca una URL ni una ruta.
- **La comprobación.** La imagen se comprueba por sus propios bytes: PNG,
  JPEG o WEBP. Cualquier otra cosa se rechaza, se etiquete como se etiquete,
  y también una vacía.
- **Las palabras.** `error_message` y `caption` llegan al modelo como una
  línea de texto ajeno, saneada.

## Crear un proveedor

<!-- doctest: cli -->
```bash
astra-plugin new my-painter --lang python --template blank --capabilities image_provider --output ./my-painter
```

`--lang` también puede ser `rust` o `typescript`. No hay plantilla de
imágenes: la capability llega mediante `--capabilities`, y el hook del
scaffold responde `not_configured` hasta que lo implementes.
`astra-plugin test` llama a `ImageGenerate` con un prompt real y a
`ImageGetModels`; un rechazo aprueba, porque es una respuesta.

`[capabilities]` es un conjunto cerrado, así que un Astra que no conoce
`image_provider` rechaza el manifiesto entero. Ningún release lo conoce
todavía, así que no hay `min_astra_version` que indicar; añade una cuando
un release incluya la capability. Guarda la clave de API del proveedor en
el propio esquema `[config]` del plugin, donde la persona la pone en la
página de plugins:

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

## La solicitud

| Campo | Valor |
|---|---|
| `prompt` | Qué dibujar, tal como lo escribió el modelo |
| `aspect_ratio` | `""` para el valor predeterminado del propio modelo, o uno de `1:1`, `16:9`, `9:16`, `4:3`, `3:4`. Dibuja con tu valor predeterminado cuando tu API no pueda expresarlo |
| `model` | El modelo que eligió la persona — un id de tu lista de `ImageGetModels`, o escrito a mano — y `""` para tu valor predeterminado |
| `input_images` | Las imágenes que la persona adjuntó para editarlas o dibujar a partir de ellas, con los bytes tal cual. Vacío salvo que el modelo sea uno que tu lista marque con `accepts_input_images` |

## La respuesta

Exactamente una imagen — bytes PNG, JPEG o WEBP, con cualquier texto que el
modelo haya escrito junto a ella como `caption` — o un rechazo. **Un
rechazo es una respuesta, no un error.** Devuélvelo; no lo lances
(`raise`/`throw`):

| `error_code` | Cuándo | Qué hace Astra |
|---|---|---|
| `quota` | El cupo de la cuenta está agotado | Prueba el siguiente proveedor; dice al modelo que el cupo está agotado, con tus palabras |
| `rate_limited` | Demasiadas imágenes ahora mismo; fija `retry_after_secs` si la API dice cuánto | Prueba el siguiente proveedor; dice al modelo que espere |
| `not_configured` | Falta un ajuste que debe hacer la persona — normalmente la clave | Prueba el siguiente proveedor; dice al modelo que el proveedor no está configurado |
| `unavailable` | Cualquier otra cosa: el servicio está caído, falló la red, la respuesta era ilegible | Prueba el siguiente proveedor |
| `refused` | Se rechazó el propio prompt — un filtro de seguridad, un rechazo suave | No prueba nada más: a otro proveedor se le pediría el mismo prompt |

`error_message` es corto, en inglés llano: el modelo lo lee. Un
`error_code` fuera de estos cinco se lee como `unavailable`. Una respuesta
sin imagen ni código se lee como un prompt rechazado, así que no se prueba
nada más — todos los SDK se niegan a enviar una así. Astra todavía no
espera `retry_after_secs` para una imagen; está en el cable para cuando lo
haga.

Lo que NO es una respuesta: una excepción lanzada, un error arrojado o un
`Err` de Rust llegan a Astra como una llamada fallida, que Astra lee como un
fallo de este plugin, y pasa al siguiente proveedor — así que un rechazo
que querías, lanzado en vez de devuelto, pierde su código. Un plugin que
declara `image_provider` y no implementa el hook responde `UNIMPLEMENTED`,
que Astra reporta como un proveedor sin configurar.

Astra espera por una imagen el menor de `plugin.call_timeout_secs` (120
segundos si no está fijado) y su propio límite: 150 segundos, o 55 mientras
el chat funciona sobre Astra AI, cuyo servidor deja de esperar a una
herramienta a los 60. Pon a la solicitud a tu servicio un tiempo de espera
dentro de eso, y responde `unavailable` cuando se dispare.

## Modelos, y editar una imagen

`ImageGetModels` es opcional. Lista los modelos que ofrece el selector — un
`id`, un `name` y si el modelo acepta imágenes para editar
(`accepts_input_images`) — y el `default_model` que se usa cuando la persona
no nombra ninguno (`""` = el primero). Astra descarta un modelo cuyo id
está vacío, tiene más de 200 caracteres o contiene un carácter de control,
e ignora un `default_model` que no está en la lista.

También es así como Astra decide si envía una imagen. Cuando la persona
adjuntó imágenes y pidió una edición, Astra pregunta primero a
`ImageGetModels`, toma el modelo que eligió la persona (si no,
`default_model`; si no, el primero), y envía TODAS las imágenes en
`input_images` solo cuando ese modelo figura con `accepts_input_images`. Si
no, dice al modelo que este proveedor no puede editar y prueba el
siguiente. A un plugin sin lista nunca se le envía una imagen para editar.

## Rust

`image_generate` en `PluginCapability` (o como `#[hook]` dentro de
`#[astra::plugin]`) toma una `ImageRequest` y devuelve
`anyhow::Result<ImageResponse>`. `ImageResponse::drawn(bytes)` lee el tipo
de la imagen a partir de sus bytes; `.with_caption(text)` añade el pie de
imagen. `ImageResponse::refuse(ImageErrorCode::…, message)` construye un
rechazo, y `.with_retry_after(secs)` va en uno `RateLimited`.
`image_models` devuelve `(models, default_model)`;
`ImageModelInfo::new(id, name).accepts_input_images()` marca un modelo que
edita. La función de relleno de abajo es donde va tu cliente HTTP — el SDK
no incluye uno.

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

Sobrescribe `image_generate(self, request)` en `Plugin`. Recibe una
`ImageRequest` y devuelve una `ImageResponse` — o los bytes de la imagen,
lo que significa que se dibujó. `ImageResponse.drawn(data, caption=…)` lee
el tipo a partir de los bytes;
`ImageResponse.refuse(code, message, retry_after_secs=0)` comprueba el
código, así que una errata falla en tu propia prueba.
`image_get_models(self)` devuelve una `ImageModelList`, o una tupla
`(models, default_model)`. El I/O bloqueante va en un hilo
(`asyncio.to_thread`): el hook comparte su bucle de eventos con cada otro
hook que sirve el plugin.

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

Dale a `plugin({...})` una sección `image` — `generate(req, ctx)` y,
opcionalmente, `models` (una lista, o `(ctx) => list`) — o sobrescribe
`imageGenerate(req)` e `imageGetModels()` en una subclase `Plugin`.
Construye la respuesta con `ImageGeneration.drawn(bytes, { caption })`, que
lee el tipo a partir de los bytes, o con `ImageGeneration.refuse(code,
message, retryAfterSecs)`; `generate` también puede devolver los bytes.

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

## Pruebas

El harness de nivel 1 de cada SDK dirige los hooks a través de la misma
proyección de cable que ve Astra — una imagen, o el rechazo en el cuerpo:

| SDK | Llamada | Devuelve |
|---|---|---|
| Rust | `running.image_generate(ImageRequest::new(..))`, `running.image_models()` | la `ImageResponse` del hook; su `(models, default_model)` |
| Python | `harness.image_generate(prompt, aspect_ratio=…, model=…, input_images=…)`, `harness.image_models()` | una `ImageResponse` leída de vuelta desde el cable; una `ImageModelList` |
| TypeScript | `harness.imageGenerate(prompt, { aspectRatio, model, inputImages })`, `harness.imageGetModels()` | una `ImageResponse` leída de vuelta desde el cable; una `ImageModelList` |

El harness envía `input_images` diga lo que diga tu lista; elegir quién las
recibe es tarea de Astra. `astra-plugin test` pide una imagen real, con 60
segundos de margen, y falla con lo que Astra leería mal o rechazaría: un
`error_code` fuera de los cinco, una respuesta sin imagen ni código, más de
una imagen, o una imagen que no es PNG, JPEG o WEBP según sus bytes. Lee la
lista de modelos del mismo modo en que Astra la admite. Luego, haz sideload
con `astra-plugin dev` en un Astra compilado con `plugin-provider-slots`.

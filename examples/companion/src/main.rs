use astra_plugin_sdk::prelude::*;

struct CompanionCat {
    i18n: I18n,
}

impl Default for CompanionCat {
    fn default() -> Self {
        // `discover()` rather than `load("locales")`: it honours
        // $ASTRA_PLUGIN_DIR when the daemon sets it, and falls back to the
        // working directory, which is the only reason the old form worked.
        Self { i18n: I18n::discover() }
    }
}

#[async_trait]
impl PluginCapability for CompanionCat {
    /// The cat has no settings — that is the whole of `NoConfig`.
    type Config = NoConfig;

    async fn ui_contributions(&self) -> Vec<UiContribution> {
        vec![UiContribution::overlay("cat-overlay", "cat.js")]
    }

    async fn on_language_changed(&self, _ctx: &PluginContext, language: &str) {
        self.i18n.set_language(language);
    }

    async fn handle_ui_call(
        &self,
        _ctx: &PluginContext,
        method: &str,
        _params_json: &str,
    ) -> Result<String, ToolError> {
        match method {
            "getRandomMessage" => {
                let nanos = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .subsec_nanos() as usize;
                // This used to be `nanos % 41`, under a comment saying it must
                // match the number of `msg.N` keys in the locale files. Nothing
                // made it match. Adding a 42nd line to en.json and ru.json would
                // have left the cat silently unable to say it, and deleting one
                // would have had `t()` return the bare key `msg.41` to a user.
                //
                // `count_prefixed` counts across the UNION of every locale
                // loaded, so a language somebody has not finished translating
                // cannot change the modulus and make two users see different
                // numbers of messages.
                let n = self.i18n.count_prefixed("msg.");
                if n == 0 {
                    // No `msg.` key loaded at all. `discover()` never fails, it
                    // just finds nothing, and `nanos % 0` panics — so this says
                    // which of the two happened instead of taking the process
                    // down inside a UI call.
                    let why = if self.i18n.load_errors().is_empty() {
                        format!(
                            "no msg.* keys in {:?}",
                            self.i18n.source_dir().unwrap_or(std::path::Path::new("locales"))
                        )
                    } else {
                        self.i18n.load_errors().join("; ")
                    };
                    return Ok(serde_json::json!({ "message": "", "error": why }).to_string());
                }
                let key = format!("msg.{}", nanos % n);
                Ok(serde_json::json!({ "message": self.i18n.t(&key) }).to_string())
            }
            _ => Err(ToolError::NotFound(format!("Unknown method: {method}"))),
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    astra_plugin_sdk::run(CompanionCat::default()).await
}

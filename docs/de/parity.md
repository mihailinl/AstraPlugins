> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../en/parity.md) maßgeblich. Die englische Seite ist GENERIERT von `tools/parity/gen.py` aus `spec/hooks.yaml` — diese Übersetzung ist eine von Hand gepflegte Momentaufnahme davon, keine weitere generierte Kopie.

# Hook-Parität

Protokoll **1** · **35** Hooks · Source of Truth [`spec/hooks.yaml`](../../spec/hooks.yaml).

Ein *Hook* ist ein RPC auf einem der beiden Plugin-seitigen Dienste.
`PluginCapabilityService` läuft **Daemon → Plugin**: dein Plugin bedient
ihn, und der Daemon ruft hinein. `PluginHostService` läuft
**Plugin → Daemon**: der Daemon bedient ihn, und dein Plugin ruft hinaus.
`PluginService` steht hier nicht — der Daemon bedient ihn für die
Astra-UI, kein Plugin fasst ihn je an.

| Spalte | Bedeutung |
|---|---|
| **Capability** | Der `[capabilities]`-Schlüssel in `plugin.toml`, zu dem dieser Hook gehört, oder `core` für Hooks, die jedes Plugin hat. |
| **Permission** | Nur `PluginHostService`. Der `[permissions]`-Schlüssel, an den der Daemon den Aufruf bindet (§5.6), oder `none`, wenn jedes Plugin ihn immer aufrufen darf. **Nicht dieselbe Frage wie Capability:** die Capability sagt, zu welchem Feature der Aufruf gehört, die Permission ist das, wozu der Nutzer zugestimmt hat, und der Daemon antwortet aus der *gewährten* Permission-Menge. Gegen die `HOST_RPC_PERMISSIONS` des Daemons durch Regel R6 geprüft. |
| **Req** | `required` — die Capability funktioniert ohne den Hook nicht. `optional` — der Daemon macht weiter, wenn er fehlt. |
| **Routing** | `live` — der Daemon ruft ihn tatsächlich auf, und die Aufrufstelle ist benannt. `unrouted` — im Proto deklariert, von niemandem aufgerufen. `deprecated` — wird ausgemustert. |
| `stable` | Das SDK bindet dieses RPC an einen Handler, der tatsächlich arbeitet — gegen seinen Quellcode durch Regel R1 von `tools/parity/check.py` geprüft, die das Dispatch-Ziel auflöst (TypeScripts `.bind(this)`, Pythons Servicer-Methode, Rusts `async fn`) und *diesen* Rumpf liest. Ob die Bindung etwas erreicht, wenn ein echter Plugin-Prozess dadurch getrieben wird, ist die Frage von Regel R7, nicht von R1. |
| `planned` | Committed, nicht ausgeliefert. Das Datum ist die Gnadenfrist-Deadline; Regel R4 lässt den Build fehlschlagen, sobald sie verstreicht. |
| `n/a` | Nicht implementiert und nicht committed. Ein registrierter Handler, dessen Rumpf nur `UNIMPLEMENTED` beantwortet, zählt als `n/a`, weil das auf der Leitung *ein fehlender Hook ist* — R1 liest den Handler-Rumpf genau dafür. |

## Befunde

Aus den Zeilen unten abgeleitet, nicht von Hand geschrieben. Jeder ist
ein Weg, auf dem der Code eines Plugin-Autors heute scheitert.

1. **`TtsSynthesizeStream` ist unrouted.** Das Proto deklariert es, und
   es gibt keine Aufrufstelle im Daemon — trotzdem in Rust, Python,
   TypeScript gebunden. Entweder verdrahten oder ausmustern; heute ist
   es ein Versprechen, das der Daemon nicht hält.
2. **`AiGetModels` ist veraltet, aber weiterhin gebunden** in Rust,
   Python, TypeScript. Behalte die Bindungen, damit ein altes Plugin
   weiterhin `UNIMPLEMENTED` statt eines Transportfehlers bekommt; füge
   keine neuen hinzu.

## PluginCapabilityService — Daemon → Plugin

| RPC | Capability | Req | Routing | Stream | Rust | Python | TypeScript | Daemon-Aufrufstelle |
|---|---|---|---|---|---|---|---|---|
| `ListTools` | `tools` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:3624` |
| `CallTool` | `tools` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7601` |
| `TtsSynthesize` | `tts` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7910` |
| `TtsSynthesizeStream` | `tts` | optional | unrouted | server | stable | stable | stable | **keine** |
| `TtsListVoices` | `tts` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7958` |
| `TtsGetConfigFields` | `tts` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8198` |
| `TtsActivate` | `tts` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7990` |
| `SttProcess` | `stt` | required | live | bidi | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8045` |
| `SttGetLanguages` | `stt` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8166` |
| `SttGetConfigFields` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8222` |
| `SttLoad` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8246` |
| `SttUnload` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8324` |
| `SttGetLoadState` | `stt` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:8275` |
| `AiComplete` | `ai_provider` | required | live | server | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/capability_bridge.rs:157` |
| `AiGetModels` | `ai_provider` | optional | deprecated | unary | stable | stable | stable | **keine** |
| `ExecuteAction` | `actions` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7755` |
| `GetPluginActionTypes` | `actions` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:3633` |
| `GetPluginTriggerTypes` | `triggers` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:3642` |
| `OnActiveTriggers` | `triggers` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:7853` |
| `GetUiContributions` | `ui_contributions` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:3651` |
| `CallFromUi` | `ui_contributions` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:3952` |
| `OnConfigChanged` | `core` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:4133` |
| `OnLanguageChanged` | `core` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:4074` |
| `Shutdown` | `core` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/instance.rs:1290` |
| `HealthCheck` | `core` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/manager.rs:4394` |

## PluginHostService — Plugin → Daemon

| RPC | Capability | Permission | Req | Routing | Stream | Rust | Python | TypeScript | Daemon-Aufrufstelle |
|---|---|---|---|---|---|---|---|---|---|
| `Register` | `core` | `none` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:1474` |
| `GetPluginSelfConfig` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2045` |
| `PluginLog` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2068` |
| `GetDaemonInfo` | `core` | `none` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2106` |
| `SetVariable` | `core` | `set_variable` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2126` |
| `SubscribeEvents` | `event_handlers` | `subscribe_events` | required | live | server | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:1663` |
| `FireTrigger` | `triggers` | `fire_trigger` | required | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:1860` |
| `SendChatMessage` | `client` | `send_chat_message` | required | live | server | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:1717` |
| `PushToUi` | `ui_contributions` | `push_to_ui` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2170` |
| `SetThemeContribution` | `ui_contributions` | `set_theme_contribution` | optional | live | unary | stable | stable | stable | `astra-rs/astra-daemon/src/plugins/host_service.rs:2201` |

## Capability-Bereitschaft

Kann ein in dieser Sprache geschriebenes Plugin diese Capability heute
überhaupt implementieren?

| Capability | Rust | Python | TypeScript |
|---|---|---|---|
| `tools` | ja | ja | ja |
| `tts` | ja | ja | ja |
| `stt` | ja | ja | ja |
| `ai_provider` | ja | ja | ja |
| `actions` | ja | ja | ja |
| `triggers` | ja | ja | ja |
| `ui_contributions` | ja | ja | ja |
| `core` | ja | ja | ja |
| `event_handlers` | ja | ja | ja |
| `client` | ja | ja | ja |

## Conformance-Abdeckung

Die 23 eingehenden Hooks, die ein Conformance-Lauf ausüben muss — jeder
`Daemon → Plugin`-Hook, den der Daemon tatsächlich aufruft.
`astra-plugin test` ruft jeden auf, den die deklarierten Capabilities
des Plugins implizieren, und sichert kein `UNIMPLEMENTED` für die
`required`-Hooks ab; `optional`-Hooks sind ausgenommen, weil
`Unimplemented → Hook fehlt` der Vorwärtskompatibilitäts-Vertrag ist und
ein Scaffold, das alles deklariert, sonst nicht von einem kaputten
Plugin zu unterscheiden wäre. Maschinenlesbare Kopie:
[`spec/generated/conformance.json`](../../spec/generated/conformance.json).

| RPC | Capability | Req | Stream | Phase |
|---|---|---|---|---|
| `ListTools` | `tools` | required | unary | probe |
| `CallTool` | `tools` | required | unary | probe |
| `TtsSynthesize` | `tts` | required | unary | probe |
| `TtsListVoices` | `tts` | required | unary | probe |
| `TtsGetConfigFields` | `tts` | optional | unary | probe |
| `TtsActivate` | `tts` | optional | unary | probe |
| `SttProcess` | `stt` | required | bidi | probe |
| `SttGetLanguages` | `stt` | required | unary | probe |
| `SttGetConfigFields` | `stt` | optional | unary | probe |
| `SttLoad` | `stt` | optional | unary | probe |
| `SttUnload` | `stt` | optional | unary | probe |
| `SttGetLoadState` | `stt` | optional | unary | probe |
| `AiComplete` | `ai_provider` | required | server | probe |
| `ExecuteAction` | `actions` | required | unary | probe |
| `GetPluginActionTypes` | `actions` | required | unary | probe |
| `GetPluginTriggerTypes` | `triggers` | required | unary | probe |
| `OnActiveTriggers` | `triggers` | optional | unary | probe |
| `GetUiContributions` | `ui_contributions` | required | unary | probe |
| `CallFromUi` | `ui_contributions` | optional | unary | probe |
| `OnConfigChanged` | `core` | optional | unary | probe |
| `OnLanguageChanged` | `core` | optional | unary | probe |
| `HealthCheck` | `core` | required | unary | probe |
| `Shutdown` | `core` | required | unary | teardown |

## Anmerkungen

- **`TtsSynthesizeStream`** — Synthetisiert eine Äußerung als Chunk-Stream, für niedrige First-Audio-Latenz. BEFUND: Es existiert keine Aufrufstelle im Daemon in astra-rs. Alle drei SDKs bedienen ihn jetzt, und nichts ruft ihn auf — die Abweichung, für deren Erkennung diese Datei existiert, ist weg, das ungeroutete RPC nicht.
- **`TtsGetConfigFields`** — Zusätzliche TTS-Settings-Felder, gerendert von DynamicField auf der Voice-Seite. Über den `optional_hook`-Helfer des Daemons geroutet (manager.rs:2878), UNIMPLEMENTED bedeutet also fehlend, und ein echter Fehler bleibt ein Fehler.
- **`TtsActivate`** — Liefert einen lizenzierten Voice-Content-Key zur einmaligen maschinengebundenen Versiegelung. Das Proto sagt, UNIMPLEMENTED werde als „keine Aktivierung nötig" behandelt; der Daemon routet es NICHT über `optional_hook` — manager.rs:2664 propagiert den Fehler, und vox_activation.rs:319 lässt die Aktivierung scheitern. Der Proto-Kommentar ist derjenige, der falsch liegt.
- **`SttProcess`** — Audio-Chunks rein, Transkript-Events raus; trägt sowohl Einmal- als auch Streaming-STT. Auch live getrieben bei manager.rs:2808. Kanalkapazität an beiden Enden ist spec/limits.yaml:stt_audio_channel_capacity.
- **`SttLoad`** — Lädt das Recognizer-Modell, mit vom Daemon aufgelöstem Pfad und GPU-Umschalter. manager.rs:2918 routet es über `optional_hook`, weshalb dies optional ist.
- **`SttGetLoadState`** — Meldet Loaded / NotLoaded / NotNeeded, damit der Daemon Idle-Unload steuern kann. manager.rs:2960 bildet einen fehlenden Hook auf NotNeeded ab, was das Verhalten vor dem Hook ist.
- **`AiComplete`** — Streamt eine Model-Completion; der einzige Weg, wie ein Plugin ein AI-Provider sein kann. Python und TypeScript binden es als Async-Generator; Rust als kanalgespeister Server-Stream, der auf den ersten Chunk wartet, bevor die Antwort geöffnet wird, sodass ein nicht überschriebener Hook weiterhin UNIMPLEMENTED beantworten kann. Alle drei SDKs binden es seit 5.4, `ai_provider` ist also in jeder Sprache implementierbar.
- **`AiGetModels`** — Listet die Modelle, die dieser Provider ausführen kann. BEFUND: in allen drei SDKs implementiert und von niemandem aufgerufen. `all_ai_providers` hartkodiert supports_model_discovery=false, der Picker fragt also nie. Im Proto als veraltet markiert; die Bindungen behalten, keine weiteren hinzufügen. Veraltet in 0.6, entfernt in 0.8, und es gibt keinen Ersatz: nichts im Daemon fragt ein Plugin, welche Modelle es hat, und AiComplete trägt das gewählte Modell in der Anfrage.
- **`OnActiveTriggers`** — Auf welche Trigger-Typen dieses Plugins ein Befehl gerade hört. manager.rs:2523 routet es über `optional_hook`.
- **`OnLanguageChanged`** — Die Astra-UI-Sprache hat sich geändert; render alles Nutzersichtbare neu. manager.rs:1133 routet es über `optional_hook`.
- **`Shutdown`** — Sauber stoppen; die Prozessgruppe wird nach der Frist getötet. Die Frist ist spec/limits.yaml:plugin_stop_grace_secs. Antworten, dann beenden.
- **`HealthCheck`** — Liveness-Probe, alle 15 s. Erforderlich im stärksten Sinne: dieser Hook ist NICHT über `optional_hook` geroutet, jeder Fehler — UNIMPLEMENTED eingeschlossen — markiert das Plugin also als tot (manager.rs:1464).
- **`Register`** — Der Handshake: das Spawn-Token beweisen, das Plugin-eigene Session-Token erhalten. Der einzige vom Auth-Interceptor ausgenommene Pfad. Jeder spätere Host-RPC muss das zurückgegebene Token als x-session-token tragen.
- **`SendChatMessage`** — Sendet eine Chat-Nachricht als dieses Plugin und streamt die Antwort des Assistenten zurück. Das Session-Token ist auf PluginHostService begrenzt, der DaemonClient-/ChatService-Weg, auf den die SDKs Autoren früher verwiesen, ist also permission_denied — dieses RPC ist der einzige funktionierende Pfad. Seit 5.4 in allen drei SDKs gebunden.
- **`PushToUi`** — Pusht ein Event in die eigenen iframes dieses Plugins — der Rückweg für CallFromUi. Jetzt in allen drei gebunden. Python hatte drei Releases lang CallFromUi und kein PushToUi, ein Python-UI-Plugin konnte also aufgerufen werden und nicht asynchron antworten.
- **`SetThemeContribution`** — Steuert Farben, Wallpaper und Shader zum aktiven Astra-Theme bei. Phase 4 klassifiziert es als hochriskant und verweigert es unterhalb von Stufe 1, sodass eine Bindung ohne die gewährte Permission ein permission_denied ist, kein neu gestrichenes Theme. Seit 5.4 in allen drei SDKs gebunden.
</content>

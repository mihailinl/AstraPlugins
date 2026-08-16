> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/hooks/rust.md) maßgeblich. Die englische Seite ist GENERIERT von `tools/parity/gen.py` aus `spec/hooks.yaml` — diese Übersetzung ist eine von Hand gepflegte Momentaufnahme davon, keine weitere generierte Kopie.

# Rust-SDK — Hook-Tabelle

Protokoll **1**. Jeder Hook, den das Rust-SDK binden kann, und ob es das
tut. Generiert aus [`spec/hooks.yaml`](../../../spec/hooks.yaml); die
sprachübergreifende Ansicht ist [`parity.md`](../parity.md).

## PluginCapabilityService — Daemon → Plugin

Diese implementierst du; der Daemon ruft sie auf.

| RPC | Capability | Erforderlich | Stream | Status | Was es tut |
|---|---|---|---|---|---|
| `ListTools` | `tools` | required | unary | stable | Die Tool-Schemas, die dieses Plugin dem Modell anbietet, einmal beim Start gelesen. |
| `CallTool` | `tools` | required | unary | stable | Führt einen Tool-Aufruf im Auftrag des Modells aus und gibt sein Ergebnis zurück. |
| `TtsSynthesize` | `tts` | required | unary | stable | Synthetisiert eine Äußerung und gibt den gesamten Puffer zurück. |
| `TtsSynthesizeStream` | `tts` | optional | server | stable | Synthetisiert eine Äußerung als Chunk-Stream, für niedrige First-Audio-Latenz. |
| `TtsListVoices` | `tts` | required | unary | stable | Die Stimmen, die dieser Provider im Voice-Settings-Picker anbietet. |
| `TtsGetConfigFields` | `tts` | optional | unary | stable | Zusätzliche TTS-Settings-Felder, gerendert von DynamicField auf der Voice-Seite. |
| `TtsActivate` | `tts` | optional | unary | stable | Liefert einen lizenzierten Voice-Content-Key zur einmaligen maschinengebundenen Versiegelung. |
| `SttProcess` | `stt` | required | bidi | stable | Audio-Chunks rein, Transkript-Events raus; trägt sowohl Einmal- als auch Streaming-STT. |
| `SttGetLanguages` | `stt` | required | unary | stable | Die Sprachcodes, die dieser Recognizer akzeptiert. |
| `SttGetConfigFields` | `stt` | optional | unary | stable | Zusätzliche STT-Settings-Felder, gerendert von DynamicField auf der Voice-Seite. |
| `SttLoad` | `stt` | optional | unary | stable | Lädt das Recognizer-Modell, mit vom Daemon aufgelöstem Pfad und GPU-Umschalter. |
| `SttUnload` | `stt` | optional | unary | stable | Entlädt das Recognizer-Modell, sodass Idle-Unload tatsächlich VRAM freigibt. |
| `SttGetLoadState` | `stt` | optional | unary | stable | Meldet Loaded / NotLoaded / NotNeeded, damit der Daemon Idle-Unload steuern kann. |
| `AiComplete` | `ai_provider` | required | server | stable | Streamt eine Model-Completion; der einzige Weg, wie ein Plugin ein AI-Provider sein kann. |
| `AiGetModels` | `ai_provider` | optional | unary | stable | Listet die Modelle, die dieser Provider ausführen kann. |
| `ExecuteAction` | `actions` | required | unary | stable | Führt eine Command-Step-Action aus, die dieses Plugin beigesteuert hat. |
| `GetPluginActionTypes` | `actions` | required | unary | stable | Die Action-Typen, die dieses Plugin zum Befehlseditor hinzufügt, beim Start gelesen. |
| `GetPluginTriggerTypes` | `triggers` | required | unary | stable | Die Trigger-Typen, die dieses Plugin zum Befehlseditor hinzufügt, beim Start gelesen. |
| `OnActiveTriggers` | `triggers` | optional | unary | stable | Auf welche Trigger-Typen dieses Plugins ein Befehl gerade hört. |
| `GetUiContributions` | `ui_contributions` | required | unary | stable | Die Seiten, Slots, Overlays und Effekte, die dieses Plugin im Astra-Fenster rendert. |
| `CallFromUi` | `ui_contributions` | optional | unary | stable | Ein Methodenaufruf vom eigenen iframe dieses Plugins in sein Backend. |
| `OnConfigChanged` | `core` | optional | unary | stable | Der Nutzer hat neue Settings gespeichert; hier ist die gesamte Config als JSON. |
| `OnLanguageChanged` | `core` | optional | unary | stable | Die Astra-UI-Sprache hat sich geändert; render alles Nutzersichtbare neu. |
| `Shutdown` | `core` | required | unary | stable | Sauber stoppen; die Prozessgruppe wird nach der Frist getötet. |
| `HealthCheck` | `core` | required | unary | stable | Liveness-Probe, alle 15 s. |

## PluginHostService — Plugin → Daemon

Diese implementiert der Daemon; du rufst sie auf.

**Capability allein reicht hier nicht.** Das sind Aufrufe, die du in den
Daemon hinein tätigst, und der Daemon beantwortet sie aus der
*gewährten* Permission-Menge (§5.6). Die Capability zu deklarieren sagt,
zu welchem Feature der Aufruf gehört; die Permission zu deklarieren ist
das, wozu der Nutzer zustimmt. Ein Plugin, das nur die Capability
deklariert, bekommt auf der Maschine des Nutzers `permission_denied`.
`none` bedeutet, jedes Plugin darf es immer aufrufen.

| RPC | Capability | Permission | Erforderlich | Stream | Status | Was es tut |
|---|---|---|---|---|---|---|
| `Register` | `core` | `none` | required | unary | stable | Der Handshake: das Spawn-Token beweisen, das Plugin-eigene Session-Token erhalten. |
| `GetPluginSelfConfig` | `core` | `none` | optional | unary | stable | Die eigenen persistierten Settings dieses Plugins lesen. |
| `PluginLog` | `core` | `none` | optional | unary | stable | Eine Zeile in den Daemon-Log-Puffer schreiben, den das Log-Panel des Plugins liest. |
| `GetDaemonInfo` | `core` | `none` | optional | unary | stable | Daemon-Version, -Zustand und gRPC-Port. |
| `SetVariable` | `core` | `set_variable` | optional | unary | stable | Eine Variable veröffentlichen, die Befehle und andere Plugins lesen können. |
| `SubscribeEvents` | `event_handlers` | `subscribe_events` | required | server | stable | Der gefilterte Daemon-Event-Stream; die gesamte event_handlers-Capability. |
| `FireTrigger` | `triggers` | `fire_trigger` | required | unary | stable | Löst einen der Trigger-Typen dieses Plugins aus und führt aus, was für Befehle darauf hören. |
| `SendChatMessage` | `client` | `send_chat_message` | required | server | stable | Sendet eine Chat-Nachricht als dieses Plugin und streamt die Antwort des Assistenten zurück. |
| `PushToUi` | `ui_contributions` | `push_to_ui` | optional | unary | stable | Pusht ein Event in die eigenen iframes dieses Plugins — der Rückweg für CallFromUi. |
| `SetThemeContribution` | `ui_contributions` | `set_theme_contribution` | optional | unary | stable | Steuert Farben, Wallpaper und Shader zum aktiven Astra-Theme bei. |

## Lücken

Keine. Das Rust-SDK bindet jeden Hook in der Spezifikation.
</content>

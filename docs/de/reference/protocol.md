> **Übersetzung.** Dies ist eine Übersetzung. Bei Abweichungen ist [`docs/en`](../../en/reference/protocol.md) maßgeblich. Die englische Seite ist GENERIERT von `tools/docgen/protocol.py` — diese Übersetzung ist eine von Hand gepflegte Momentaufnahme davon, keine weitere generierte Kopie.

# Protokoll-Referenz

Protokoll-Generation **1**. 10 Dienste, 158 RPCs. Quelle:
[`proto/plugin.proto`](../../../proto/plugin.proto), ein generierter
Ausschnitt von Astras `astra.proto`
(`source-sha256: 3588e1647aca5a7a…`), gepinnt von
[`proto/PROTO_VERSION`](../../../proto/PROTO_VERSION) auf
`sha256:2bccd2f5cd787f03…`. Jede gevendorte Kopie in den drei SDKs hat
denselben Hash; `tools/check-proto.sh` ist das, was das bestätigt.

## Die drei Plugin-Dienste

| Dienst | Richtung | RPCs | Wer ihn bedient |
|---|---|---|---|
| [`PluginCapabilityService`](#plugincapabilityservice) | Daemon → Plugin | 25 | dein Plugin |
| [`PluginHostService`](#pluginhostservice) | Plugin → Daemon | 10 | der Daemon |
| [`PluginService`](#pluginservice) | UI → Daemon | 23 | der Daemon |

Die Protokoll-Generation ist der Vertrag. Ein Plugin sendet sie in
`PluginRegisterRequest.protocol_version`, und der Daemon antwortet mit
seiner eigenen Untergrenze in
`PluginRegisterResponse.min_supported_protocol`; `sdk_name` und
`sdk_version` reisen für die Triage mit und sperren nichts.

## PluginCapabilityService

**Dein Plugin bedient das.** Der Daemon ist der Client: er ruft hinein,
um ein Tool auszuführen, Sprache zu synthetisieren, dir ein Event zu
übergeben. Jedes RPC hier ist ein Hook, den du implementierst, und
`UNIMPLEMENTED` ist das Wort des Protokolls für *dieses Plugin hat
diesen Hook nicht* — nicht für einen Fehler.

| RPC | Capability | Request | Response | Stream | Geroutet | Was es tut |
|---|---|---|---|---|---|---|
| `ListTools` | `tools` | `Empty` | `PluginToolListResponse` | unary | live | Die Tool-Schemas, die dieses Plugin dem Modell anbietet, einmal beim Start gelesen. |
| `CallTool` | `tools` | `PluginCallToolRequest` | `PluginCallToolResponse` | unary | live | Führt einen Tool-Aufruf im Auftrag des Modells aus und gibt sein Ergebnis zurück. |
| `TtsSynthesize` | `tts` | `PluginTtsSynthesizeRequest` | `PluginTtsSynthesizeResponse` | unary | live | Synthetisiert eine Äußerung und gibt den gesamten Puffer zurück. |
| `TtsSynthesizeStream` | `tts` | `PluginTtsSynthesizeRequest` | `PluginAudioChunk` | server | unrouted | Synthetisiert eine Äußerung als Chunk-Stream, für niedrige First-Audio-Latenz. |
| `TtsListVoices` | `tts` | `Empty` | `PluginTtsVoicesResponse` | unary | live | Die Stimmen, die dieser Provider im Voice-Settings-Picker anbietet. |
| `TtsGetConfigFields` | `tts` | `Empty` | `PluginConfigFieldsResponse` | unary | live | Zusätzliche TTS-Settings-Felder, gerendert von DynamicField auf der Voice-Seite. |
| `TtsActivate` | `tts` | `PluginTtsActivateRequest` | `PluginTtsActivateResponse` | unary | live | Liefert einen lizenzierten Voice-Content-Key zur einmaligen maschinengebundenen Versiegelung. |
| `SttProcess` | `stt` | `PluginAudioChunk` | `PluginSttEvent` | bidi | live | Audio-Chunks rein, Transkript-Events raus; trägt sowohl Einmal- als auch Streaming-STT. |
| `SttGetLanguages` | `stt` | `Empty` | `PluginSttLanguagesResponse` | unary | live | Die Sprachcodes, die dieser Recognizer akzeptiert. |
| `SttGetConfigFields` | `stt` | `Empty` | `PluginConfigFieldsResponse` | unary | live | Zusätzliche STT-Settings-Felder, gerendert von DynamicField auf der Voice-Seite. |
| `SttLoad` | `stt` | `SttLoadRequest` | `Empty` | unary | live | Lädt das Recognizer-Modell, mit vom Daemon aufgelöstem Pfad und GPU-Umschalter. |
| `SttUnload` | `stt` | `Empty` | `Empty` | unary | live | Entlädt das Recognizer-Modell, sodass Idle-Unload tatsächlich VRAM freigibt. |
| `SttGetLoadState` | `stt` | `Empty` | `SttLoadStateResponse` | unary | live | Meldet Loaded / NotLoaded / NotNeeded, damit der Daemon Idle-Unload steuern kann. |
| `AiComplete` | `ai_provider` | `PluginAiCompleteRequest` | `PluginAiStreamChunk` | server | live | Streamt eine Model-Completion; der einzige Weg, wie ein Plugin ein AI-Provider sein kann. |
| `AiGetModels` *(veraltet)* | `ai_provider` | `Empty` | `PluginAiModelsResponse` | unary | deprecated | Listet die Modelle, die dieser Provider ausführen kann. |
| `ExecuteAction` | `actions` | `PluginExecuteActionRequest` | `PluginExecuteActionResponse` | unary | live | Führt eine Command-Step-Action aus, die dieses Plugin beigesteuert hat. |
| `GetPluginActionTypes` | `actions` | `Empty` | `PluginActionTypesResponse` | unary | live | Die Action-Typen, die dieses Plugin zum Befehlseditor hinzufügt, beim Start gelesen. |
| `GetPluginTriggerTypes` | `triggers` | `Empty` | `PluginTriggerTypesResponse` | unary | live | Die Trigger-Typen, die dieses Plugin zum Befehlseditor hinzufügt, beim Start gelesen. |
| `GetUiContributions` | `ui_contributions` | `Empty` | `PluginUiContributionsResponse` | unary | live | Die Seiten, Slots, Overlays und Effekte, die dieses Plugin im Astra-Fenster rendert. |
| `CallFromUi` | `ui_contributions` | `PluginUiCallRequest` | `PluginUiCallResponse` | unary | live | Ein Methodenaufruf vom eigenen iframe dieses Plugins in sein Backend. |
| `OnConfigChanged` | `core` | `PluginConfigChangedMsg` | `Empty` | unary | live | Der Nutzer hat neue Settings gespeichert; hier ist die gesamte Config als JSON. |
| `OnActiveTriggers` | `triggers` | `PluginActiveTriggersMsg` | `Empty` | unary | live | Auf welche Trigger-Typen dieses Plugins ein Befehl gerade hört. |
| `OnLanguageChanged` | `core` | `LanguageChangedMsg` | `Empty` | unary | live | Die Astra-UI-Sprache hat sich geändert; render alles Nutzersichtbare neu. |
| `Shutdown` | `core` | `Empty` | `Empty` | unary | live | Sauber stoppen; die Prozessgruppe wird nach der Frist getötet. |
| `HealthCheck` | `core` | `Empty` | `PluginHealthResponse` | unary | live | Liveness-Probe, alle 15 s. |

## PluginHostService

**Der Daemon bedient das.** Dein Plugin ist der Client. `Register` ist
der Bootstrap: er beweist das Spawn-Token, das der Daemon dem Prozess
übergeben hat, und gibt ein Session-Token zurück, und ist der eine Pfad,
den der Auth-Interceptor des Daemons ausnimmt. Jeder andere Aufruf trägt
dieses Token, und die gesperrten werden zusätzlich gegen die
Permissions geprüft, die der *Nutzer* gewährt hat — eine andere Frage
als die von dir deklarierten Capabilities.

| RPC | Permission | Request | Response | Stream | Geroutet | Was es tut |
|---|---|---|---|---|---|---|
| `Register` | `none` | `PluginRegisterRequest` | `PluginRegisterResponse` | unary | live | Der Handshake: das Spawn-Token beweisen, das Plugin-eigene Session-Token erhalten. |
| `SubscribeEvents` | `subscribe_events` | `PluginEventFilter` | `PluginEventMsg` | server | live | Der gefilterte Daemon-Event-Stream; die gesamte event_handlers-Capability. |
| `SendChatMessage` | `send_chat_message` | `PluginChatRequest` | `PluginChatChunk` | server | live | Sendet eine Chat-Nachricht als dieses Plugin und streamt die Antwort des Assistenten zurück. |
| `FireTrigger` | `fire_trigger` | `PluginFireTriggerRequest` | `Empty` | unary | live | Löst einen der Trigger-Typen dieses Plugins aus und führt aus, was für Befehle darauf hören. |
| `GetPluginSelfConfig` | `none` | `PluginSelfIdRequest` | `PluginSelfConfigResponse` | unary | live | Die eigenen persistierten Settings dieses Plugins lesen. |
| `PluginLog` | `none` | `PluginLogRequest` | `Empty` | unary | live | Eine Zeile in den Daemon-Log-Puffer schreiben, den das Log-Panel des Plugins liest. |
| `GetDaemonInfo` | `none` | `Empty` | `PluginDaemonInfoResponse` | unary | live | Daemon-Version, -Zustand und gRPC-Port. |
| `SetVariable` | `set_variable` | `PluginSetVariableRequest` | `Empty` | unary | live | Eine Variable veröffentlichen, die Befehle und andere Plugins lesen können. |
| `SetThemeContribution` | `set_theme_contribution` | `PluginThemeContribution` | `Empty` | unary | live | Steuert Farben, Wallpaper und Shader zum aktiven Astra-Theme bei. |
| `PushToUi` | `push_to_ui` | `PluginUiPushRequest` | `Empty` | unary | live | Pusht ein Event in die eigenen iframes dieses Plugins — der Rückweg für CallFromUi. |

`none` bedeutet, jedes Plugin darf es immer aufrufen — die
Bootstrap-Menge, für die der Daemon überhaupt keine
Permission-Prüfung durchführt. Das ist eine Aussage über den Daemon,
kein Achselzucken: die Spalte stammt aus
[`spec/hooks.yaml`](../../../spec/hooks.yaml), und Paritätsregel R6
prüft jede ihrer Zeilen gegen `HOST_RPC_PERMISSIONS` in
`plugins/host_service.rs` des Daemons, der Tabelle, die
`require_permission` liest. Ein Host-RPC ohne Zeile dort ist ungesperrt,
und R6 nennt das einen Sicherheitsbefund, keinen Spec-Tippfehler.

Das Gate antwortet am *Anfang* eines Aufrufs. `SubscribeEvents` startet
einmal und läuft, bis das Plugin sich beendet, sodass der Daemon den
Stream beendet — mit `permission_denied` und einem
Teardown-Grund-Trailer — wenn eine Gewährung verengt, die Zustimmung
zurückgezogen oder das Plugin widerrufen wird. Eine entzogene Permission
ist also von einer abgebrochenen Verbindung unterscheidbar.

## PluginService

**Keine Seite eines Plugins.** Der Daemon bedient das für die Astra-UI:
Installation, Import, Deinstallation, Provenienz, Zustimmung, Logs. Kein
Plugin ruft es je auf, und kein SDK bindet es; es steht hier, weil es
die Oberfläche ist, durch die die Installation deines Plugins bei einem
Nutzer tatsächlich läuft.

| RPC | Request | Response | Stream | Was es tut |
|---|---|---|---|---|
| `ListPlugins` | `Empty` | `PluginListResponse` | unary | Listet alle installierten Plugins mit Status |
| `InstallPlugin` | `InstallPluginRequest` | `PluginStatusMsg` | unary | Installiert ein Plugin aus der Registry |
| `InstallPluginStream` | `InstallPluginRequest` | `PluginInstallProgress` | server | Installiert ein Plugin aus der Registry und meldet jede Phase im Verlauf. |
| `CancelPluginInstall` | `PluginIdRequest` | `CancelPluginInstallResponse` | unary | Bricht eine von InstallPluginStream gestartete Installation ab. |
| `UninstallPlugin` | `UninstallPluginRequest` | `UninstallPluginResponse` | unary | Entfernt ein Plugin und entscheidet separat, was mit seinen Settings passiert. |
| `ReportPlugin` | `ReportPluginRequest` | `ReportPluginResponse` | unary | Meldet ein Plugin — und stellt es, falls der Nutzer darum bittet, zuerst HIER unter Quarantäne. |
| `SetPluginEnabled` | `SetPluginEnabledRequest` | `Empty` | unary | Aktiviert/deaktiviert ein Plugin |
| `StartPlugin` | `PluginIdRequest` | `Empty` | unary | Startet ein gestopptes Plugin |
| `StopPlugin` | `PluginIdRequest` | `Empty` | unary | Stoppt ein laufendes Plugin |
| `GetPluginConfig` | `PluginIdRequest` | `PluginConfigResponse` | unary | Holt Plugin-Config-Schema + aktuelle Werte |
| `UpdatePluginConfig` | `UpdatePluginConfigRequest` | `Empty` | unary | Aktualisiert Plugin-Config |
| `BrowsePluginRegistry` | `PluginBrowseRequest` | `PluginBrowseResponse` | unary | Durchsucht die Plugin-Registry |
| `CheckPluginUpdates` | `Empty` | `PluginUpdatesResponse` | unary | Prüft installierte Plugins auf Updates |
| `UpdatePlugin` | `PluginIdRequest` | `PluginStatusMsg` | unary | Aktualisiert ein Plugin auf die neueste Version |
| `SideloadPlugin` | `SideloadPluginRequest` | `PluginStatusMsg` | unary | Sideloaded ein Plugin von einem lokalen Pfad (Dev-Modus) |
| `ImportPluginFile` | `ImportPluginFileRequest` | `PluginStatusMsg` | unary | Importiert ein Plugin aus einer lokalen .astraplugin-ZIP-Datei |
| `InspectPluginFile` | `InspectPluginFileRequest` | `PluginFileInspection` | unary | Liest eine `.astraplugin`-Datei, OHNE sie zu installieren, sodass das Einwilligungsblatt aus §4.3 auch auf dem Importpfad gezeigt werden kann. |
| `ResolvePendingUpdate` | `ResolvePendingUpdateRequest` | `PluginStatusMsg` | unary | §4.5/§4.6. |
| `GetPluginLogs` | `PluginLogsRequest` | `PluginLogsResponse` | unary | Holt Logs von einem Plugin (letzte N Zeilen) |
| `GetPluginProvenance` | `PluginProvenanceRequest` | `PluginProvenanceMsg` | unary | Alles, was Astra darüber aufgezeichnet hat, woher ein INSTALLIERTES Plugin stammt — Produktionsplan §4.2, das Provenance-Panel. |
| `GetAllUiContributions` | `Empty` | `AllUiContributionsResponse` | unary | Holt alle UI-Contributions von allen laufenden Plugins |
| `GetActiveThemes` | `Empty` | `ActiveThemesResponse` | unary | Holt aktive Theme-Contributions von Plugins |
| `CallPluginFromUi` | `CallPluginFromUiRequest` | `CallPluginFromUiResponse` | unary | Leitet einen UI-Aufruf an das Backend eines Plugins weiter |

## Der Rest des Ausschnitts

Das Plugin-Proto trägt auch Astras eigene client-seitige Dienste, weil
ein `client`-Plugin — eines, das eine Chat-Oberfläche irgendwo hinstellt,
wo Astra nicht ist, wie das Telegram-Beispiel — den Daemon über sie mit
dem `Daemon`-Handle des SDK treibt. Sie sind keine Plugin-Hooks, und
keine Capability impliziert sie.

| Dienst | RPCs |
|---|---|
| `CoreService` | 8 |
| `ChatService` | 12 |
| `VoiceService` | 34 |
| `CommandService` | 13 |
| `ConfigService` | 25 |
| `MediaService` | 5 |
| `MonitorService` | 3 |

Vollständige Signaturen stehen in
[`proto/plugin.proto`](../../../proto/plugin.proto); diese Seite wiederholt
nicht die gut 100 RPCs, die ein Plugin nur über den typisierten Wrapper
des SDK erreicht.

## Ausmusterungen

| RPC | Warum |
|---|---|
| `PluginCapabilityService.AiGetModels` | VERALTET — der Daemon hat keine Aufrufstelle und keine Möglichkeit, die Antwort anzuzeigen. |

Ein veraltetes RPC bleibt deklariert. Es zu entfernen würde die
generierten Trait-Implementierungen brechen, die jedes SDK ausgibt, und
ein Plugin, das eines wählt, sollte weiterhin `UNIMPLEMENTED` bekommen —
was *fehlend* bedeutet — statt eines Transportfehlers.
</content>

use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tracing::{info, warn};

use crate::types::ChatKey;

/// Persistent state — who the bot belongs to, and which Astra conversation each
/// Telegram chat is talking into.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct BotState {
    /// The Telegram user this bot answers, learned from the first message it
    /// sees, and consulted **only while the username allowlist is empty**.
    ///
    /// It is what keeps "the bot serves every chat you write in" from also
    /// meaning "the bot serves every stranger who finds it". Version 0.2 bound
    /// itself to one CHAT for the same reason; binding to the person instead is
    /// what lets that person have as many chats as they like without opening the
    /// bridge to anybody else.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub owner_user_id: Option<u64>,

    /// The single chat version 0.2 bound itself to.
    ///
    /// Read until an owner is learned: it is what says which chat may speak, so
    /// an install that was bound to one chat keeps exactly the reach it had
    /// rather than opening up the moment the new version starts. Never written
    /// again.
    #[serde(default, skip_serializing_if = "is_zero")]
    pub chat_id: i64,

    /// Version 0.2's single conversation, drained into `conversations` by
    /// [`BotState::load`] and never written again — see the migration there.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    conversation_id: Option<String>,

    /// The Astra conversation each Telegram chat is writing into, as the daemon
    /// resolved it — learned from the reply stream, not chosen here. A chat with
    /// no row opens a fresh conversation on its next message (a first message,
    /// or `/new`).
    ///
    /// Keyed by [`ChatKey`]'s string form, because JSON object keys are strings.
    /// A key this build cannot read is kept and ignored rather than dropped: it
    /// costs nothing, and rewriting somebody's file to remove a row it did not
    /// understand is how a state file loses data.
    #[serde(default)]
    pub conversations: BTreeMap<String, String>,

    /// Chats whose next message should also **name** the Telegram topic it is
    /// written in.
    ///
    /// Set by `/new` (on the topic it just opened, which Telegram made it name
    /// before there was anything to name it after) and by `/clear` (on the topic
    /// it was typed in, whose conversation starts over and whose name should say
    /// so). Nothing else puts a chat in here, which is what keeps the bridge from
    /// renaming a topic somebody made and named themselves.
    ///
    /// Persisted because the two halves are separate events: a restart between
    /// the command and the message that answers it would otherwise leave the
    /// topic called "New chat" for good.
    #[serde(default, skip_serializing_if = "BTreeSet::is_empty")]
    pub awaiting_title: BTreeSet<String>,
}

fn is_zero(id: &i64) -> bool {
    *id == 0
}

impl BotState {
    /// Path to the state file (next to the executable).
    pub fn state_file_path() -> PathBuf {
        let exe_dir = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.to_path_buf()))
            .unwrap_or_else(|| PathBuf::from("."));
        exe_dir.join("state.json")
    }

    /// Load state from disk, or return default.
    ///
    /// **Version 0.2's one conversation becomes version 0.3's row for the chat
    /// it belonged to.** Nothing is lost in an update: the chat the bridge was
    /// bound to carries on in the same Astra conversation, with the same memory,
    /// and the user sees no break. (Version 0.1's `topic_map` was dropped on the
    /// way to 0.2 — the ids in it were never real, because the calls that minted
    /// them were refused — and serde ignores the field this build no longer
    /// knows.)
    pub fn load(path: &std::path::Path) -> Self {
        let mut state = match std::fs::read_to_string(path) {
            Ok(data) => match serde_json::from_str::<BotState>(&data) {
                Ok(state) => state,
                Err(e) => {
                    warn!("Failed to parse state file: {e}");
                    BotState::default()
                }
            },
            Err(_) => {
                info!("No state file found, starting fresh");
                BotState::default()
            }
        };

        if let Some(conversation) = state.conversation_id.take() {
            if state.chat_id != 0 {
                let key = ChatKey::new(state.chat_id, None).to_string();
                info!("Carrying the 0.2 conversation {conversation} over as chat {key}'s");
                state.conversations.entry(key).or_insert(conversation);
            }
            // Written back so the migration happens once, and so the drained
            // field leaves the file rather than sitting there reading like state.
            state.save(path);
        }

        info!(
            "Loaded state: owner={}, {} chat(s) with a conversation",
            state
                .owner_user_id
                .map_or_else(|| "not bound yet".to_string(), |id| id.to_string()),
            state.conversations.len(),
        );
        state
    }

    /// Save state to disk.
    pub fn save(&self, path: &std::path::Path) {
        let data = serde_json::to_string_pretty(self).unwrap_or_default();
        if let Err(e) = std::fs::write(path, data) {
            warn!("Failed to save state: {e}");
        }
    }

    /// The Astra conversation this chat is talking into, if it has one.
    pub fn conversation_of(&self, chat: ChatKey) -> Option<String> {
        self.conversations.get(&chat.to_string()).cloned()
    }

    /// Remember (or forget) the conversation one chat writes into, and persist
    /// it. A no-op when nothing changed, so the common case — every reply chunk
    /// carrying the id this chat already holds — costs no disk write.
    pub fn set_conversation(&mut self, chat: ChatKey, conversation_id: Option<String>) {
        let key = chat.to_string();
        let changed = match &conversation_id {
            Some(id) => self.conversations.insert(key, id.clone()).as_deref() != Some(id.as_str()),
            None => self.conversations.remove(&key).is_some(),
        };
        if changed {
            self.save(&Self::state_file_path());
        }
    }

    /// Should this chat's next message name the topic it is in?
    pub fn awaits_title(&self, chat: ChatKey) -> bool {
        self.awaiting_title.contains(&chat.to_string())
    }

    /// Mark (or unmark) this chat as waiting for its topic's name, and persist
    /// it. A no-op when nothing changed, like [`Self::set_conversation`].
    pub fn set_awaiting_title(&mut self, chat: ChatKey, awaiting: bool) {
        let key = chat.to_string();
        let changed = if awaiting {
            self.awaiting_title.insert(key)
        } else {
            self.awaiting_title.remove(&key)
        };
        if changed {
            self.save(&Self::state_file_path());
        }
    }

    /// Remember the person this bot answers, and persist it.
    pub fn set_owner(&mut self, user_id: u64) {
        if self.owner_user_id == Some(user_id) {
            return;
        }
        self.owner_user_id = Some(user_id);
        self.save(&Self::state_file_path());
    }
}

/// A state fixture for the tests in this crate, which live in two modules: the
/// migration below, and [`crate::bot`]'s tests of who may talk to the bot. It is
/// here rather than there because `conversation_id` is private on purpose — it is
/// drained by `load` and read nowhere else — and a struct literal outside this
/// module cannot name it even to skip it.
#[cfg(test)]
impl BotState {
    pub(crate) fn bound(owner_user_id: Option<u64>, chat_id: i64) -> Self {
        Self {
            owner_user_id,
            chat_id,
            conversation_id: None,
            conversations: BTreeMap::new(),
            awaiting_title: BTreeSet::new(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A temp path nothing else in this test run is using.
    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "astra-telegram-state-{name}-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).expect("a temp directory");
        dir.join("state.json")
    }

    /// An install that was bound to one chat keeps its conversation, and its
    /// memory, rather than starting over on the first message after an update.
    #[test]
    fn version_0_2_s_one_conversation_becomes_that_chat_s_row() {
        let path = scratch("migration");
        std::fs::write(
            &path,
            "{\"chat_id\":811091354,\
             \"conversation_id\":\"7fd22c5b-0000-0000-0000-000000000001\"}",
        )
        .expect("writing the fixture");

        let state = BotState::load(&path);
        assert_eq!(
            state
                .conversation_of(ChatKey::new(811091354, None))
                .as_deref(),
            Some("7fd22c5b-0000-0000-0000-000000000001"),
        );
        assert_eq!(state.chat_id, 811091354, "the old binding still gates");

        // And the migration is written back, so it happens once rather than on
        // every start — with the drained field gone from the file.
        let written = std::fs::read_to_string(&path).expect("the file was rewritten");
        assert!(!written.contains("conversation_id"), "{written}");
        assert!(written.contains("811091354"), "{written}");

        let _ = std::fs::remove_file(&path);
    }

    /// A forum topic is its own chat, and the group it is in is not the same row.
    #[test]
    fn a_chat_and_one_of_its_topics_are_different_rows() {
        let mut state = BotState::default();
        let group = ChatKey::new(-1001, None);
        let topic = ChatKey::new(-1001, Some(57));

        state.conversations.insert(group.to_string(), "a".into());
        state.conversations.insert(topic.to_string(), "b".into());

        assert_eq!(state.conversation_of(group).as_deref(), Some("a"));
        assert_eq!(state.conversation_of(topic).as_deref(), Some("b"));
        assert_eq!(topic.to_string(), "-1001:57");
        assert_eq!("-1001:57".parse::<ChatKey>(), Ok(topic));
        assert_eq!("-1001".parse::<ChatKey>(), Ok(group));
    }

    /// A topic marked for naming is still marked after a restart — the command
    /// and the message that names the topic are two separate events, and the one
    /// in between is what loses a flag that only lived in memory.
    #[test]
    fn a_topic_waiting_for_its_name_survives_a_restart() {
        let path = scratch("awaiting-title");
        let topic = ChatKey::new(-1001, Some(57));

        let mut state = BotState::default();
        state.awaiting_title.insert(topic.to_string());
        state.save(&path);

        let mut reloaded = BotState::load(&path);
        assert!(reloaded.awaits_title(topic));
        assert!(
            !reloaded.awaits_title(ChatKey::new(-1001, None)),
            "one topic, not the group it is in"
        );

        reloaded.awaiting_title.remove(&topic.to_string());
        reloaded.save(&path);
        let written = std::fs::read_to_string(&path).expect("the file is there");
        assert!(
            !written.contains("awaiting_title"),
            "an empty set leaves the file rather than sitting in it: {written}"
        );

        let _ = std::fs::remove_file(&path);
    }

    /// `/new` forgets one chat's conversation and leaves every other chat alone.
    /// The whole of `/new` is this line, so a bug here is `/new` clearing the
    /// wrong chat's memory.
    #[test]
    fn forgetting_one_chat_leaves_the_others() {
        let mut state = BotState::default();
        let mine = ChatKey::new(1, None);
        let theirs = ChatKey::new(2, None);
        state.conversations.insert(mine.to_string(), "a".into());
        state.conversations.insert(theirs.to_string(), "b".into());

        state.set_conversation(mine, None);

        assert_eq!(state.conversation_of(mine), None);
        assert_eq!(state.conversation_of(theirs).as_deref(), Some("b"));
    }
}

//! Astra Plugin SDK — build plugins for Astra in Rust.
//!
//! # Quick Start
//!
//! ```rust,no_run
//! use astra_plugin_sdk::prelude::*;
//!
//! struct MyPlugin;
//!
//! #[async_trait]
//! impl PluginCapability for MyPlugin {
//!     async fn list_tools(&self) -> Vec<ToolDef> {
//!         vec![ToolDef {
//!             name: "hello".into(),
//!             description: "Say hello".into(),
//!             parameters_json: "{}".into(),
//!         }]
//!     }
//!
//!     async fn call_tool(&self, name: &str, args: &str) -> ToolResult {
//!         ToolResult::ok(format!("Hello from {name}!"))
//!     }
//! }
//!
//! #[tokio::main]
//! async fn main() {
//!     astra_plugin_sdk::run(MyPlugin).await.unwrap();
//! }
//! ```

pub mod proto {
    tonic::include_proto!("astra");
}

mod capability;
mod daemon_client;
pub mod events;
mod host_client;
mod runner;

pub use capability::*;
pub use daemon_client::DaemonClient;
pub use host_client::HostClient;
pub use runner::run;

/// Re-exports for convenience.
pub mod prelude {
    pub use crate::capability::*;
    pub use crate::daemon_client::DaemonClient;
    pub use crate::events::ChatSyncEvent;
    pub use crate::host_client::HostClient;
    pub use crate::run;
    pub use async_trait::async_trait;
}

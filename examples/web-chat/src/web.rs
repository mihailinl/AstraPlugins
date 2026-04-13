use std::sync::Arc;

use axum::extract::ws::{Message, WebSocket};
use axum::extract::{State, WebSocketUpgrade};
use axum::response::{Html, IntoResponse};
use axum::routing::get;
use axum::Router;
use futures::{SinkExt, StreamExt};
use tracing::info;

use crate::{AppState, SOURCE_ID};

const PORT: u16 = 9090;

pub async fn run_server(state: Arc<AppState>) -> anyhow::Result<()> {
    let app = Router::new()
        .route("/", get(index_handler))
        .route("/ws", get(ws_handler))
        .with_state(state);

    let listener = tokio::net::TcpListener::bind(format!("127.0.0.1:{PORT}")).await?;
    info!("Web chat UI at http://127.0.0.1:{PORT}");
    axum::serve(listener, app).await?;
    Ok(())
}

async fn index_handler() -> impl IntoResponse {
    Html(HTML_PAGE)
}

async fn ws_handler(ws: WebSocketUpgrade, State(state): State<Arc<AppState>>) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_ws(socket, state))
}

async fn handle_ws(socket: WebSocket, state: Arc<AppState>) {
    let (mut ws_tx, mut ws_rx) = socket.split();
    let mut event_rx = state.event_tx.subscribe();

    // Forward broadcast messages → WebSocket (messages already have their own "type" field)
    let tx_task = tokio::spawn(async move {
        loop {
            match event_rx.recv().await {
                Ok(json) => {
                    if ws_tx.send(Message::Text(json.into())).await.is_err() {
                        break;
                    }
                }
                Err(tokio::sync::broadcast::error::RecvError::Lagged(n)) => {
                    tracing::warn!("WebSocket broadcast lagged by {n} events");
                    continue;
                }
                Err(tokio::sync::broadcast::error::RecvError::Closed) => break,
            }
        }
    });

    // Handle commands from WebSocket
    while let Some(Ok(msg)) = ws_rx.next().await {
        if let Message::Text(text) = msg {
            let text: &str = &text;
            if let Ok(cmd) = serde_json::from_str::<serde_json::Value>(text) {
                let cmd_type = cmd.get("type").and_then(|v| v.as_str()).unwrap_or("");
                match cmd_type {
                    "list_conversations" => {
                        let mut d = state.daemon.lock().await;
                        if let Some(ref mut dc) = *d {
                            match dc.list_conversations().await {
                                Ok(resp) => {
                                    let convs: Vec<serde_json::Value> = resp.conversations.iter().map(|c| {
                                        serde_json::json!({
                                            "id": c.id,
                                            "title": c.title,
                                        })
                                    }).collect();
                                    let reply = serde_json::json!({ "type": "conversations", "data": convs });
                                    let _ = state.event_tx.send(reply.to_string());
                                }
                                Err(e) => {
                                    let _ = state.event_tx.send(serde_json::json!({ "type": "error", "data": e.to_string() }).to_string());
                                }
                            }
                        }
                    }
                    "send_message" => {
                        let text = cmd.get("text").and_then(|v| v.as_str()).unwrap_or("");
                        let conv_id = cmd.get("conversation_id").and_then(|v| v.as_str()).unwrap_or("");
                        if !text.is_empty() {
                            let mut d = state.daemon.lock().await;
                            if let Some(ref mut dc) = *d {
                                match dc.send_message_full(text, false, SOURCE_ID, conv_id).await {
                                    Ok(mut stream) => {
                                        drop(d); // release lock before streaming
                                        while let Some(chunk) = tokio_stream::StreamExt::next(&mut stream).await {
                                            match chunk {
                                                Ok(c) => {
                                                    let chunk_json = serde_json::json!({
                                                        "type": "chunk",
                                                        "data": {
                                                            "message_id": c.message_id,
                                                            "conversation_id": c.conversation_id,
                                                            "chunk": format_chunk(&c),
                                                        }
                                                    });
                                                    let _ = state.event_tx.send(chunk_json.to_string());
                                                }
                                                Err(e) => {
                                                    let _ = state.event_tx.send(serde_json::json!({ "type": "error", "data": e.to_string() }).to_string());
                                                    break;
                                                }
                                            }
                                        }
                                        let _ = state.event_tx.send(serde_json::json!({ "type": "done" }).to_string());
                                    }
                                    Err(e) => {
                                        let _ = state.event_tx.send(serde_json::json!({ "type": "error", "data": e.to_string() }).to_string());
                                    }
                                }
                            }
                        }
                    }
                    "load_history" => {
                        let conv_id = cmd.get("conversation_id").and_then(|v| v.as_str()).unwrap_or("");
                        let mut d = state.daemon.lock().await;
                        if let Some(ref mut dc) = *d {
                            match dc.get_history(conv_id, 50, 0).await {
                                Ok(resp) => {
                                    let msgs: Vec<serde_json::Value> = resp.messages.iter().map(|m| {
                                        serde_json::json!({
                                            "id": m.id,
                                            "role": if m.role == 0 { "user" } else { "assistant" },
                                            "content": m.content,
                                        })
                                    }).collect();
                                    let reply = serde_json::json!({ "type": "history", "data": msgs });
                                    let _ = state.event_tx.send(reply.to_string());
                                }
                                Err(e) => {
                                    let _ = state.event_tx.send(serde_json::json!({ "type": "error", "data": e.to_string() }).to_string());
                                }
                            }
                        }
                    }
                    _ => {}
                }
            }
        }
    }

    tx_task.abort();
}

fn format_chunk(c: &astra_plugin_sdk::proto::ChatStreamChunk) -> serde_json::Value {
    use astra_plugin_sdk::proto::chat_stream_chunk::Chunk;
    match &c.chunk {
        Some(Chunk::Text(t)) => serde_json::json!({ "kind": "text", "content": t }),
        Some(Chunk::Thinking(t)) => serde_json::json!({ "kind": "thinking", "content": t }),
        Some(Chunk::Tool(t)) => serde_json::json!({ "kind": "tool", "name": t.name, "completed": t.completed }),
        Some(Chunk::Error(e)) => serde_json::json!({ "kind": "error", "content": e }),
        Some(Chunk::Done(_)) => serde_json::json!({ "kind": "done" }),
        Some(Chunk::Voice(v)) => serde_json::json!({ "kind": "voice", "content": v }),
        None => serde_json::json!({ "kind": "empty" }),
    }
}

const HTML_PAGE: &str = r#"<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Astra Web Chat (Test Client)</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0; height: 100vh; display: flex; }
#sidebar { width: 260px; background: #16213e; border-right: 1px solid #333; display: flex; flex-direction: column; }
#sidebar h2 { padding: 16px; font-size: 14px; color: #888; border-bottom: 1px solid #333; }
#conv-list { flex: 1; overflow-y: auto; }
.conv-item { padding: 12px 16px; cursor: pointer; border-bottom: 1px solid #222; font-size: 13px; }
.conv-item:hover { background: #1a1a3e; }
.conv-item.active { background: #0f3460; }
#main { flex: 1; display: flex; flex-direction: column; }
#header { padding: 12px 20px; background: #16213e; border-bottom: 1px solid #333; font-weight: 600; font-size: 14px; }
#messages { flex: 1; overflow-y: auto; padding: 20px; }
.msg { margin-bottom: 16px; max-width: 80%; }
.msg.user { margin-left: auto; }
.msg .bubble { padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
.msg.user .bubble { background: #0f3460; }
.msg.assistant .bubble { background: #2a2a4a; }
.msg .meta { font-size: 11px; color: #666; margin-bottom: 2px; }
.msg.user .meta { text-align: right; }
.sync-badge { background: #e94560; color: white; font-size: 10px; padding: 1px 6px; border-radius: 8px; margin-left: 6px; }
#input-area { padding: 16px 20px; background: #16213e; border-top: 1px solid #333; display: flex; gap: 10px; }
#input-area input { flex: 1; padding: 10px 14px; border: 1px solid #333; border-radius: 8px; background: #1a1a2e; color: #e0e0e0; font-size: 14px; outline: none; }
#input-area button { padding: 10px 20px; background: #0f3460; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
#input-area button:hover { background: #e94560; }
#log { position: fixed; bottom: 0; right: 0; width: 400px; max-height: 200px; overflow-y: auto; background: #000a; color: #0f0; font-family: monospace; font-size: 11px; padding: 8px; z-index: 100; }
</style>
</head><body>
<div id="sidebar">
  <h2>CONVERSATIONS <button onclick="loadConversations()" style="float:right;background:#0f3460;color:white;border:none;padding:2px 8px;border-radius:4px;cursor:pointer">↻</button></h2>
  <div id="conv-list"></div>
</div>
<div id="main">
  <div id="header">Select a conversation or start typing</div>
  <div id="messages"></div>
  <div id="input-area">
    <input id="msg-input" placeholder="Type a message..." onkeydown="if(event.key==='Enter')sendMsg()">
    <button onclick="sendMsg()">Send</button>
  </div>
</div>
<div id="log"></div>
<script>
let ws, activeConvId = '', sourceId = 'web-chat-client';
let streamingContent = '';

function log(s) {
  const el = document.getElementById('log');
  el.textContent += new Date().toLocaleTimeString() + ' ' + s + '\n';
  el.scrollTop = el.scrollHeight;
}

function connect() {
  ws = new WebSocket('ws://' + location.host + '/ws');
  ws.onopen = () => { log('WS connected'); loadConversations(); };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    log('← ' + msg.type + (msg.data?.role ? ' role=' + msg.data.role : '') + (msg.data?.source_id ? ' src=' + msg.data.source_id : ''));
    switch(msg.type) {
      case 'conversations': renderConversations(msg.data); break;
      case 'history': renderHistory(msg.data); break;
      case 'sync': handleSync(msg.data); break;
      case 'chunk': handleChunk(msg.data); break;
      case 'done': finalizeDone(); break;
      case 'error': log('ERROR: ' + msg.data); break;
    }
  };
  ws.onclose = () => { log('WS closed, reconnecting...'); setTimeout(connect, 2000); };
}

function loadConversations() {
  ws.send(JSON.stringify({ type: 'list_conversations' }));
}

function renderConversations(convs) {
  const el = document.getElementById('conv-list');
  el.innerHTML = convs.map(c =>
    `<div class="conv-item ${c.id===activeConvId?'active':''}" onclick="selectConv('${c.id}','${esc(c.title)}')">${c.title||'Untitled'}</div>`
  ).join('');
}

function selectConv(id, title) {
  activeConvId = id;
  document.getElementById('header').textContent = title || 'Chat';
  document.getElementById('messages').innerHTML = '';
  renderConversations([]); // will re-highlight after load
  ws.send(JSON.stringify({ type: 'load_history', conversation_id: id }));
  loadConversations();
}

function renderHistory(msgs) {
  const el = document.getElementById('messages');
  el.innerHTML = msgs.map(m =>
    `<div class="msg ${m.role}"><div class="meta">${m.role}</div><div class="bubble">${esc(m.content)}</div></div>`
  ).join('');
  el.scrollTop = el.scrollHeight;
}

function handleSync(data) {
  // Only show for active conversation (or if no conversation selected)
  if (activeConvId && data.conversation_id !== activeConvId) return;
  if (data.source_id === sourceId) return; // skip own

  const el = document.getElementById('messages');
  let existing = document.getElementById('sync-' + data.id);
  if (existing) {
    existing.querySelector('.bubble').textContent = data.content || '...';
  } else {
    const div = document.createElement('div');
    div.className = 'msg ' + data.role;
    div.id = 'sync-' + data.id;
    div.innerHTML = `<div class="meta">${data.role} <span class="sync-badge">SYNC</span></div><div class="bubble">${esc(data.content||'...')}</div>`;
    el.appendChild(div);
  }
  el.scrollTop = el.scrollHeight;
}

function handleChunk(data) {
  if (data.chunk.kind === 'text') {
    streamingContent += data.chunk.content;
    // Update conversation ID if auto-created
    if (data.conversation_id && !activeConvId) {
      activeConvId = data.conversation_id;
      loadConversations();
    }
    const el = document.getElementById('messages');
    let existing = document.getElementById('streaming');
    if (existing) {
      existing.querySelector('.bubble').textContent = streamingContent;
    } else {
      const div = document.createElement('div');
      div.className = 'msg assistant';
      div.id = 'streaming';
      div.innerHTML = `<div class="meta">assistant</div><div class="bubble">${esc(streamingContent)}</div>`;
      el.appendChild(div);
    }
    el.scrollTop = el.scrollHeight;
  } else if (data.chunk.kind === 'tool') {
    log('Tool: ' + data.chunk.name + (data.chunk.completed ? ' ✔' : ' ...'));
  }
}

function finalizeDone() {
  const el = document.getElementById('streaming');
  if (el) el.id = '';
  streamingContent = '';
}

function sendMsg() {
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';

  // Show user message immediately
  const el = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg user';
  div.innerHTML = `<div class="meta">user</div><div class="bubble">${esc(text)}</div>`;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;

  ws.send(JSON.stringify({ type: 'send_message', text, conversation_id: activeConvId }));
}

function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

connect();
</script>
</body></html>
"#;

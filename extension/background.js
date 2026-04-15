/**
 * Background service worker.
 * Maintains WebSocket connection to Python backend.
 * Routes commands to the content script running on StreetEasy tabs.
 *
 * MV3 service workers get killed after ~30s of inactivity.
 * We use two keepalive strategies:
 *   1. chrome.alarms (fires every 25s) — wakes the worker even if killed
 *   2. WebSocket ping every 20s — keeps the WS connection active
 */

let ws = null;
let reconnectTimer = null;
let pingTimer = null;
const DEFAULT_WS_URL = "ws://localhost:8765";

async function getWsUrl() {
  const { wsUrl } = await chrome.storage.local.get("wsUrl");
  return (wsUrl && wsUrl.trim()) || DEFAULT_WS_URL;
}

// Reconnect whenever the user updates the configured URL
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.wsUrl) {
    console.log("[BG] WS URL changed — reconnecting");
    if (ws) { try { ws.close(); } catch (_) {} }
    ws = null;
    connect();
  }
});

// Track the active tab we're controlling
let activeTabId = null;

// ─── Keepalive: chrome.alarms wakes the service worker periodically ───

chrome.alarms.create("keepalive", { periodInMinutes: 0.4 }); // ~24 seconds

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "keepalive") {
    // This fires even if the service worker was killed and restarted.
    // Reconnect WebSocket if it's gone.
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.log("[BG] Alarm: WebSocket not open — reconnecting");
      connect();
    }
  }
});

// ─── WebSocket connection ───

async function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  // Clean up any dead socket
  if (ws) {
    try { ws.close(); } catch (_) {}
    ws = null;
  }

  const url = await getWsUrl();
  try {
    ws = new WebSocket(url);
    console.log("[BG] Connecting to", url);
  } catch (e) {
    console.error("[BG] WebSocket creation failed:", e);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.log("[BG] Connected to backend");
    clearReconnectTimer();
    startPing();
    sendToBackend({ type: "extension_ready" });
    broadcastStatus(true);
  };

  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      console.error("[BG] Invalid JSON from backend:", event.data);
      return;
    }
    // Ignore pong responses (keepalive)
    if (msg.type === "pong") return;
    console.log("[BG] Received command:", msg.type);
    handleCommand(msg);
  };

  ws.onclose = () => {
    console.log("[BG] Disconnected from backend");
    ws = null;
    stopPing();
    broadcastStatus(false);
    scheduleReconnect();
  };

  ws.onerror = (err) => {
    console.error("[BG] WebSocket error:", err);
    try { ws.close(); } catch (_) {}
  };
}

function scheduleReconnect() {
  clearReconnectTimer();
  reconnectTimer = setTimeout(() => connect(), 3000);
}

function clearReconnectTimer() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

// ─── Ping: keeps WebSocket alive and prevents Chrome from sleeping the worker ───

function startPing() {
  stopPing();
  pingTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, 20000); // every 20 seconds
}

function stopPing() {
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
}

// ─── Helpers ───

function sendToBackend(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

function broadcastStatus(connected) {
  chrome.runtime.sendMessage({ type: "ws_status", connected }).catch(() => {});
}

// ─── Command Handlers ───

async function handleCommand(msg) {
  const cmdId = msg.cmd_id; // every command carries a unique ID

  switch (msg.type) {
    case "navigate":
      await cmdNavigate(msg, cmdId);
      break;
    case "check_captcha":
    case "solve_captcha":
    case "search_and_navigate":
    case "click_show_more":
    case "extract_data":
      await cmdForwardToContent(msg, cmdId);
      break;
    case "ping":
      sendToBackend({ type: "pong", cmd_id: cmdId });
      break;
    default:
      console.warn("[BG] Unknown command:", msg.type);
  }
}

async function cmdNavigate(msg, cmdId) {
  const url = msg.url;
  if (!url) {
    sendToBackend({ type: "error", cmd_id: cmdId, message: "No URL provided" });
    return;
  }

  try {
    const tabs = await chrome.tabs.query({ url: "https://streeteasy.com/*" });
    let tab;

    if (tabs.length > 0) {
      tab = await chrome.tabs.update(tabs[0].id, { url, active: true });
    } else {
      tab = await chrome.tabs.create({ url, active: true });
    }

    activeTabId = tab.id;

    // Wait for page to finish loading
    await new Promise((resolve) => {
      chrome.tabs.onUpdated.addListener(function listener(tabId, info) {
        if (tabId === activeTabId && info.status === "complete") {
          chrome.tabs.onUpdated.removeListener(listener);
          resolve();
        }
      });
    });

    // Give React time to render
    await new Promise((r) => setTimeout(r, 3000));

    sendToBackend({ type: "navigate_done", cmd_id: cmdId, url, tabId: activeTabId });
  } catch (err) {
    sendToBackend({ type: "error", cmd_id: cmdId, message: `Navigate failed: ${err.message}` });
  }
}

async function cmdForwardToContent(msg, cmdId) {
  if (!activeTabId) {
    sendToBackend({ type: "error", cmd_id: cmdId, message: "No active tab" });
    return;
  }

  try {
    const response = await chrome.tabs.sendMessage(activeTabId, msg);
    // Attach the cmd_id to the content script's response
    response.cmd_id = cmdId;
    sendToBackend(response);
  } catch (err) {
    sendToBackend({
      type: "error",
      cmd_id: cmdId,
      command: msg.type,
      message: `Content script error: ${err.message}`,
    });
  }
}

// ─── Popup communication ───

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "get_status") {
    (async () => {
      const wsUrl = await getWsUrl();
      sendResponse({
        connected: ws && ws.readyState === WebSocket.OPEN,
        activeTabId,
        wsUrl,
      });
    })();
    return true;
  }
  if (msg.type === "connect") {
    connect();
    sendResponse({ ok: true });
    return true;
  }
  if (msg.type === "disconnect") {
    if (ws) ws.close();
    sendResponse({ ok: true });
    return true;
  }
});

// ─── Permission: alarms ───
// manifest.json must include "alarms" in permissions

// Auto-connect on startup
connect();

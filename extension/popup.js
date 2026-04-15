const DEFAULT_WS_URL = "ws://localhost:8765";

const dot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const wsUrlInput = document.getElementById("wsUrl");
const savedNote = document.getElementById("savedNote");
const logEl = document.getElementById("log");

function log(msg) {
  const ts = new Date().toLocaleTimeString();
  logEl.textContent += `${ts} ${msg}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}

function updateUI(connected) {
  dot.className = "dot " + (connected ? "on" : "off");
  statusText.textContent = connected ? "Connected to backend" : "Disconnected";
}

function flashSaved() {
  savedNote.classList.add("show");
  setTimeout(() => savedNote.classList.remove("show"), 1500);
}

// Load current URL + status
chrome.runtime.sendMessage({ type: "get_status" }, (res) => {
  if (!res) return;
  updateUI(res.connected);
  wsUrlInput.value = res.wsUrl || DEFAULT_WS_URL;
});

// Listen for live status changes
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "ws_status") {
    updateUI(msg.connected);
    log(msg.connected ? "Connected" : "Disconnected");
  }
});

document.getElementById("btnSave").addEventListener("click", () => {
  let url = wsUrlInput.value.trim();
  if (!url) url = DEFAULT_WS_URL;

  if (!/^wss?:\/\//i.test(url)) {
    log("Error: URL must start with ws:// or wss://");
    return;
  }

  chrome.storage.local.set({ wsUrl: url }, () => {
    flashSaved();
    log(`Saved: ${url}`);
    // background.js listens to storage.onChanged and reconnects automatically
  });
});

document.getElementById("btnReset").addEventListener("click", () => {
  wsUrlInput.value = DEFAULT_WS_URL;
  chrome.storage.local.set({ wsUrl: DEFAULT_WS_URL }, () => {
    flashSaved();
    log("Reset to default");
  });
});

document.getElementById("btnConnect").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "connect" }, () => log("Connecting..."));
});

document.getElementById("btnDisconnect").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "disconnect" }, () => log("Disconnecting..."));
});

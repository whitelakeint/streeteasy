const dot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const logEl = document.getElementById("log");

function log(msg) {
  logEl.textContent += msg + "\n";
  logEl.scrollTop = logEl.scrollHeight;
}

function updateUI(connected) {
  dot.className = "dot " + (connected ? "on" : "off");
  statusText.textContent = connected ? "Connected to backend" : "Disconnected";
}

// Get initial status
chrome.runtime.sendMessage({ type: "get_status" }, (res) => {
  if (res) updateUI(res.connected);
});

// Listen for status changes
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "ws_status") {
    updateUI(msg.connected);
    log(msg.connected ? "Connected" : "Disconnected");
  }
});

document.getElementById("btnConnect").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "connect" }, () => log("Connecting..."));
});

document.getElementById("btnDisconnect").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "disconnect" }, () => log("Disconnecting..."));
});

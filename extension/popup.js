const $ = (id) => document.getElementById(id);

chrome.runtime.sendMessage({ type: "health" }, (r) => {
  const ok = r && r.ok;
  $("dot").className = "dot " + (ok ? "ok" : "bad");
  $("server").textContent = ok ? "Local server running" : "Server off: run python src/autofill_server.py";
});

chrome.storage.local.get({ auto: true }, ({ auto }) => ($("auto").checked = auto));
$("auto").addEventListener("change", (e) => chrome.storage.local.set({ auto: e.target.checked }));

async function inTab(command) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const isNaukri = tab.url && tab.url.includes("naukri.com");
  if (isNaukri) {
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["naukri.js"] });
    } catch (e) { /* guard */ }
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (cmd) => window.postMessage({ naukrifill: cmd }, "*"),
      args: [command === "refill" ? "refill" : command],
    }).catch(() => {});
  } else {
    // inject on pages not covered by the manifest (company-hosted forms); the script guards against double-load
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id, allFrames: true }, files: ["content.js"] });
    } catch (e) { /* frames we cannot access */ }
    await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: (cmd) => window.postMessage({ jobfill: cmd }, "*"),
      args: [command],
    }).catch(() => {});
  }
  window.close();
}
$("fill").addEventListener("click", () => inTab("refill"));
$("clear").addEventListener("click", () => inTab("clear"));

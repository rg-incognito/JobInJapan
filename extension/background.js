// JobFill service worker: talks to the local server (python src/autofill_server.py) for the content script.
const SERVER = "http://127.0.0.1:8765";

async function post(path, body) {
  const r = await fetch(SERVER + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} -> HTTP ${r.status}`);
  return r.json();
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  (async () => {
    if (msg.type === "context") {
      const urls = [sender.tab && sender.tab.url, sender.url, msg.frameUrl].filter(Boolean);
      try {
        const ctx = await post("/context", { urls, page_text: msg.pageText || "" });
        // cache profile + rules so the extension still fills basics if the server is down
        chrome.storage.local.set({ cache: { profile: ctx.profile, rules: ctx.rules } });
        reply({ ok: true, ctx, topUrl: sender.tab && sender.tab.url });
      } catch (e) {
        const { cache } = await chrome.storage.local.get("cache");
        if (cache) reply({ ok: true, offline: true, ctx: { ...cache, app_rules: [], job: null }, topUrl: sender.tab && sender.tab.url });
        else reply({ ok: false, error: String(e) });
      }
    } else if (msg.type === "report") {
      try {
        const r = await post("/report", { ...msg.payload, url_top: sender.tab && sender.tab.url, frame_url: sender.url });
        if (sender.tab) {
          const n = (msg.payload.report.needs || []).length + (msg.payload.report.consent || []).length;
          chrome.action.setBadgeText({ tabId: sender.tab.id, text: n ? String(n) : "✓" });
          chrome.action.setBadgeBackgroundColor({ tabId: sender.tab.id, color: n ? "#d97706" : "#16a34a" });
        }
        reply({ ok: true, saved: r.saved });
      } catch (e) {
        reply({ ok: false, error: String(e) });
      }
    } else if (msg.type === "learn") {
      try {
        const r = await post("/learn", { ...msg.payload, url_top: sender.tab && sender.tab.url });
        reply({ ok: true, ...r });
      } catch (e) {
        reply({ ok: false, error: String(e) });
      }
    } else if (msg.type === "applied") {
      try {
        const r = await post("/applied", { ...msg.payload, url_top: sender.tab && sender.tab.url });
        reply({ ok: true, ...r });
        // a tab JobFill submitted on its own is closed a few seconds after the confirmation page
        if (msg.close_tab && r.applied && sender.tab) setTimeout(() => chrome.tabs.remove(sender.tab.id).catch(() => {}), 6000);
      } catch (e) {
        reply({ ok: false, error: String(e) });
      }
    } else if (msg.type === "health") {
      try {
        const r = await fetch(SERVER + "/health");
        reply({ ok: r.ok });
      } catch (e) {
        reply({ ok: false });
      }
    }
  })();
  return true; // async reply
});

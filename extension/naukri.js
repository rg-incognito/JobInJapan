// naukri.js — NaukriFill content script
// Handles Naukri.com's Easy Apply flows:
//   Mode A1: Chatbot / AI-apply  (sequential Q&A, chips + text inputs)
//   Mode A2: Quick-Apply popup   (traditional form, multiple fields at once)
// Mode B (Apply on company website) → new tab → content.js handles the ATS form there.

(() => {
  if (window.__naukrifill) return;
  window.__naukrifill = true;

  // ── State ────────────────────────────────────────────────────────────────
  const S = {
    ctx: null, running: false, panelRoot: null, panelShadow: null,
    filled: 0, needs: 0, lastQ: '', answeredQs: new Set(),
    chatObs: null, modalEl: null, pageTimer: null,
  };

  const sleep  = ms => new Promise(r => setTimeout(r, ms));
  const norm   = s  => (s || '').replace(/[\s*✱]+/g, ' ').trim();
  const low    = s  => norm(s).toLowerCase();

  // ── Load profile from background → local server ───────────────────────
  async function loadCtx() {
    if (S.ctx) return S.ctx;
    try {
      const r = await chrome.runtime.sendMessage({
        type: 'context', frameUrl: location.href,
        pageText: (document.title + ' ' + (document.body?.innerText?.slice(0, 1500) || '')).trim(),
      });
      if (r?.ok) S.ctx = r.ctx;
    } catch (e) { console.warn('[NaukriFill] context error:', e.message); }
    return S.ctx;
  }

  function prof(key) { return S.ctx?.profile?.[key] ?? null; }

  // ── Question matcher ──────────────────────────────────────────────────
  // Returns { key, value, pickRxs? } or null
  function matchQ(text) {
    const t   = low(text);
    const p   = S.ctx?.profile || {};
    const ctc = p.current_ctc_lpa || String(p.current_ctc_inr_lpa?.fixed || 12);
    const exp = p.expected_ctc_lpa || '24';
    const nd  = p.notice_period_days || 60;
    const yr  = p.years_experience || 3;

    // ── CTC — current (must precede generic salary check) ──
    if (/current.{0,30}(ctc|salary|package)\b|fixed.{0,10}(ctc|salary)|present.{0,20}(ctc|salary)|last\s+drawn/i.test(t)
        && !/expected|desired|hike|increment|how\s+much/i.test(t))
      return { key: 'current_ctc', value: ctc, pickRxs: [new RegExp('^\\s*' + ctc + '\\s*$'), /\b12\b/] };

    // ── CTC — expected ──
    if (/expected.{0,30}(ctc|salary|package)\b|desired.{0,20}(ctc|salary)\b|expectations?\s+(on|for).{0,15}(ctc|salary)|how\s+much.{0,20}expect/i.test(t))
      return { key: 'expected_ctc', value: exp, pickRxs: [new RegExp('^\\s*' + exp + '\\s*$'), /\b24\b/] };

    // ── Annual package / hike ──
    if (/annual\s+(package|salary|ctc)/i.test(t))
      return { key: 'annual_pkg', value: exp };
    if (/expected\s+hike|hike.{0,20}percent/i.test(t))
      return { key: 'hike', value: '50', pickRxs: [/50%|40.{0,3}60|30.{0,3}50/] };

    // ── Notice period ──
    if (/notice\s+period|how\s+soon|when\s+(can|could|would)\s+you\s+(join|start)|available\s+to\s+(join|start)|joining\s+(time|date)|earliest\s+(start|joining)/i.test(t)
        && !/start\s+date\s+(year|month)|graduat|education|degree/i.test(t)) {
      const picks = [/60\s*(days?)?$/i, /2\s*months?$/i, /1[\s-]*2\s*months?/i, /more\s+than\s+1\s*month/i];
      if (Math.round(nd / 30) === 1) picks.push(/30\s*days?|1\s*month/i);
      return { key: 'notice', value: String(nd), pickRxs: picks };
    }

    // ── Total experience (not tech-specific) ──
    if (/total.{0,20}(work\s+|professional\s+)?experience|years?.{0,10}of.{0,10}experience|how\s+many\s+years|experience\s+in\s+years/i.test(t)
        && !/with|in\s+(java|python|spring|aws|react|node|angular|kubernetes|sql|go|ruby|php|typescript)\b/i.test(t))
      return { key: 'experience', value: String(yr), pickRxs: [/^3\s*(years?|yrs?)?$/i, /2[\s-]+3/i, /3[\s-]+5/i, /2\+/i] };

    // ── Tech-specific experience — Java / Spring / Python / JS (3 yrs honest) ──
    if (/years?.{0,20}(exp(erience)?).{0,20}(java(?!script)|spring\b|spring\s*boot|python|javascript|js\b|node\.?js|sql|postgres)/i.test(t)
        || /(java(?!script)|spring\b|spring\s*boot|python|javascript|js\b|node\.?js|sql|postgres).{0,20}years?.{0,20}(exp(erience)?)/i.test(t))
      return { key: 'tech_exp', value: String(yr), pickRxs: [/^3\s*(years?|yrs?)?$/i, /2[\s-]+3/i, /3[\s-]+5/i] };

    // ── Current location / city ──
    if (/(current|present).{0,20}(city|location)|where.{0,20}(based|located|living)|residing\s+in/i.test(t)) {
      const city = p.city || 'Pune';
      return { key: 'city', value: city, pickRxs: [/pune/i, /maharashtra/i, /india/i] };
    }

    // ── Preferred work mode ──
    if (/preferred.{0,20}(work\s+)?(mode|type)|work\s+from\s+(home|office)|remote\s+or\s+onsite/i.test(t))
      return { key: 'work_mode', value: 'Hybrid', pickRxs: [/hybrid/i, /both/i] };

    // ── Willing to relocate ──
    if (/willing.{0,20}relocat|ready.{0,20}relocat|open.{0,20}relocat/i.test(t))
      return { key: 'relocate', value: 'Yes', pickRxs: [/^yes/i] };

    // ── Currently employed ──
    if (/(currently|presently).{0,20}(employed|working)|are\s+you\s+(currently\s+)?working/i.test(t))
      return { key: 'employed', value: 'Yes', pickRxs: [/^yes/i, /employed/i, /working/i] };

    // ── Current company ──
    if (/current\s+(company|employer|organization)|where.{0,20}(currently\s+work|working\s+now)/i.test(t))
      return { key: 'company', value: p.current_employer || 'Sincro, a DealerOn company' };

    // ── Current title / designation ──
    if (/current\s+(designation|role|position|title)|present\s+(designation|role|position)/i.test(t))
      return { key: 'title', value: p.current_title || 'Software Engineer' };

    // ── Graduation year ──
    if (/graduat.{0,20}(year|date)|year\s+of\s+(graduation|passing|completion)/i.test(t))
      return { key: 'grad_year', value: '2023', pickRxs: [/2023/] };

    // ── Education / degree level ──
    if (/highest.{0,20}(education|qualification|degree)|degree\s+level/i.test(t))
      return { key: 'degree', value: "Bachelor's", pickRxs: [/bachelor/i, /b\.?tech/i, /b\.?e\b/i, /undergrad/i] };

    // ── Gender (Indian forms) ──
    if (/^gender\b|your\s+gender|gender\s*:/i.test(t))
      return { key: 'gender', value: 'Male', pickRxs: [/^male\b/i, /\bmale\b(?!.*fe)/i] };

    // ── Serving notice currently ──
    if (/currently.{0,20}serving.{0,20}notice|serving.{0,20}notice.{0,20}period/i.test(t))
      return { key: 'serving_notice', value: 'No', pickRxs: [/^no/i, /not\s+serving/i] };

    // ── Immediate joiner ──
    if (/immediate.{0,20}join|join.{0,20}immediately|start.{0,20}immediately/i.test(t))
      return { key: 'immediate', value: 'No', pickRxs: [/^no/i] };

    // ── Work permit / authorization (India context) ──
    if (/(work|employment).{0,20}(permit|authorization|visa|eligib)/i.test(t))
      return { key: 'work_perm', value: 'Indian Citizen', pickRxs: [/indian\s*citizen/i, /^yes/i] };

    // ── Cover note ──
    if (/cover.{0,10}(note|letter)|why.{0,20}(apply|interested|this\s+role)|tell\s+us.{0,20}(yourself|about\s+you)/i.test(t)) {
      const note = `I am a Software Engineer with ${yr} years of experience in Java, Spring Boot, Python, and AI/LLM development. `
        + `I am excited about this opportunity and believe my backend engineering skills and experience building production systems align well with the role.`;
      return { key: 'cover', value: note };
    }

    // ── Reason for change / leaving ──
    if (/reason.{0,20}(change|leaving|switch|looking)|why.{0,20}(looking|leaving|change|switch)/i.test(t)) {
      return { key: 'reason', value: p.reason_looking_now_script
        || 'I want to work on AI-powered products and grow in a more product-driven international engineering environment.' };
    }

    return null;
  }

  // ── React-compatible input setter ──────────────────────────────────────
  function setVal(el, val) {
    const proto  = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(el, val); else el.value = val;
    el.dispatchEvent(new Event('input',  { bubbles: true, composed: true }));
    el.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
  }

  // ── Fill <select> ───────────────────────────────────────────────────────
  function fillSel(sel, match) {
    const opts = [...sel.options];
    for (const rx of (match.pickRxs || [])) {
      const i = opts.findIndex(o => rx.test(norm(o.text)));
      if (i > 0) { sel.value = opts[i].value; sel.dispatchEvent(new Event('change', { bubbles: true })); return true; }
    }
    const vl = low(match.value);
    const i = opts.findIndex(o => low(o.text).startsWith(vl) || low(o.text).includes(vl));
    if (i > 0) { sel.value = opts[i].value; sel.dispatchEvent(new Event('change', { bubbles: true })); return true; }
    return false;
  }

  // ── Outline marker ───────────────────────────────────────────────────────
  function mark(el, s) {
    const c = { filled: '#16a34a', needs: '#d97706', kept: '#16a34a', skip: '#94a3b8' }[s];
    if (c) {
      el.style.setProperty('outline',        `2px solid ${c}`, 'important');
      el.style.setProperty('outline-offset', '2px',            'important');
    }
  }

  // ── Panel (Shadow DOM) ──────────────────────────────────────────────────
  function initPanel() {
    if (S.panelRoot) return;
    S.panelRoot = document.createElement('div');
    S.panelRoot.id = '__naukrifill_host';
    S.panelRoot.style.cssText =
      'all:initial;position:fixed;right:14px;bottom:80px;z-index:2147483647;pointer-events:auto';
    S.panelShadow = S.panelRoot.attachShadow({ mode: 'closed' });
    (document.body || document.documentElement).appendChild(S.panelRoot);
  }

  function renderPanel(msg) {
    if (!S.panelShadow) return;
    S.panelShadow.innerHTML = `
<style>
  .w{font:12px/1.4 system-ui,sans-serif;background:#fff;color:#111;border:1px solid #d1d5db;
     border-radius:10px;box-shadow:0 4px 20px rgba(0,0,0,.18);width:260px;overflow:hidden}
  .h{padding:8px 12px;background:#0f172a;color:#fff;display:flex;justify-content:space-between;align-items:center}
  .ht{font-size:12px;font-weight:700}.hs{font-size:10px;color:#94a3b8;margin-top:1px}
  .bd{padding:8px 12px}
  .stats{display:flex;gap:16px;margin-bottom:6px}
  .st .n{font-size:20px;font-weight:700;line-height:1}
  .st .l{font-size:10px;color:#666;margin-top:1px}
  .gn{color:#16a34a}.am{color:#d97706}
  .msg{font-size:11px;color:#555;padding:4px 0;border-top:1px solid #f0f0f0;word-break:break-word;max-height:60px;overflow:hidden}
  .btn{font:11px system-ui;border:0;border-radius:5px;padding:4px 9px;cursor:pointer;background:#2563eb;color:#fff}
  .sec{background:#334155}
  .min .bd{display:none}
</style>
<div class="w" id="pnl">
  <div class="h">
    <div><div class="ht">NaukriFill</div><div class="hs">JobFill for Naukri</div></div>
    <div style="display:flex;gap:5px">
      <button class="btn" id="rfill" title="Refill">↺</button>
      <button class="btn sec" id="tog" title="Minimise">–</button>
    </div>
  </div>
  <div class="bd">
    <div class="stats">
      <div class="st"><div class="n gn">${S.filled}</div><div class="l">filled</div></div>
      <div class="st"><div class="n am">${S.needs}</div><div class="l">need you</div></div>
    </div>
    <div class="msg" title="${msg.replace(/"/g, '&quot;')}">${msg.replace(/</g,'&lt;')}</div>
  </div>
</div>`;
    S.panelShadow.getElementById('rfill').onclick = () => detectAndFill(true);
    S.panelShadow.getElementById('tog').onclick   = () => S.panelShadow.getElementById('pnl').classList.toggle('min');
  }

  const status = msg => { if (S.panelShadow) renderPanel(msg); };

  // ── QUICK-APPLY FORM handler ────────────────────────────────────────────
  function getLabel(el) {
    if (el.placeholder) return norm(el.placeholder);
    const al = el.getAttribute('aria-label');
    if (al) return norm(al);
    if (el.id) {
      try {
        const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (lbl) return norm(lbl.textContent);
      } catch {}
    }
    let p = el.parentElement;
    for (let i = 0; p && i < 5; i++, p = p.parentElement) {
      const lbl = p.querySelector('label');
      if (lbl && !lbl.contains(el)) return norm(lbl.textContent);
      for (const ch of p.children) {
        if (ch !== el && !ch.contains(el) && ch.children.length === 0) {
          const t = norm(ch.textContent);
          if (t.length > 2 && t.length < 100) return t;
        }
      }
    }
    return norm(el.name || el.id || '');
  }

  async function fillQuickForm(modal) {
    const els = modal.querySelectorAll(
      'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=checkbox]):not([type=radio]):not([disabled]),' +
      'select:not([disabled]),' +
      'textarea:not([disabled])'
    );
    let filled = 0, needs = 0;
    for (const el of els) {
      if (!el.offsetParent) continue;
      const label = getLabel(el);
      if (!label) continue;
      if (el.tagName !== 'SELECT' && el.value && !el.dataset.nfF) { mark(el, 'kept'); continue; }
      const m = matchQ(label);
      if (!m) { mark(el, 'needs'); needs++; continue; }
      let ok = false;
      if (el.tagName === 'SELECT') {
        ok = fillSel(el, m);
      } else {
        const isNum = el.type === 'number' || el.inputMode === 'numeric' || el.inputMode === 'decimal';
        const v = isNum ? m.value.replace(/[^\d.]/g, '') : m.value;
        if (v) { setVal(el, v); el.dataset.nfF = '1'; ok = true; }
      }
      mark(el, ok ? 'filled' : 'needs');
      if (ok) filled++; else needs++;
    }
    S.filled = filled; S.needs = needs;
    return { filled, needs };
  }

  // ── CHATBOT handler ─────────────────────────────────────────────────────
  // The chatbot signals it is waiting by showing a visible, enabled input or option chips.

  function findChatInput(modal) {
    return modal.querySelector(
      'input.chatbot_Input,input[class*="chatInput"],input[class*="chat-input"],' +
      'input[class*="chatbot-input"],input[class*="chatbot_input"],' +
      'input[placeholder*="type" i],input[placeholder*="message" i],input[placeholder*="enter" i],' +
      'textarea[class*="chat"],textarea[class*="chatbot"],' +
      'input[type=number]:not([disabled]):not([readonly]),' +
      'input[type=text]:not([disabled]):not([readonly])'
    );
  }

  function findSendBtn(modal) {
    const all = [...modal.querySelectorAll('button,[role=button]')].filter(b => b.offsetParent);
    for (const b of all) {
      const s = ((b.className || '') + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.title || '')).toLowerCase();
      if (/\bsend\b|\bsubmit\b|\bnext\b|\bproceed\b|\bcontinue\b|\bgo\b/.test(s)) return b;
    }
    const area = modal.querySelector('[class*="input"],[class*="bottom"],[class*="footer"],[class*="send"]');
    if (area) {
      const btns = [...area.querySelectorAll('button,[role=button]')].filter(b => b.offsetParent);
      if (btns.length) return btns[btns.length - 1];
    }
    const icon = [...modal.querySelectorAll('button')].filter(b => b.offsetParent && b.querySelector('svg'));
    if (icon.length) return icon[icon.length - 1];
    return null;
  }

  function findChips(modal) {
    return [...modal.querySelectorAll(
      '[class*="chip"],[class*="Chip"],[class*="option-btn"],[class*="optionBtn"],' +
      '[class*="quick-reply"],[class*="quickReply"],[class*="quick_reply"],' +
      '[class*="choice-btn"],[class*="choiceBtn"],[class*="chatbot-option"],' +
      '[class*="ssrc-quick"],[class*="reply-btn"],[class*="replyBtn"]'
    )].filter(el => {
      if (!el.offsetParent) return false;
      const t = norm(el.textContent).trim();
      return t.length > 0 && t.length < 60;
    });
  }

  function getLastBotMessage(modal) {
    const sels = [
      '[class*="receive"],[class*="Receive"]',
      '[class*="bot-msg"],[class*="botMsg"],[class*="bot_msg"]',
      '[class*="ai-msg"],[class*="system-msg"],[class*="ssrc-receive"]',
      '[class*="incoming"],[class*="left-msg"]',
    ];
    for (const sel of sels) {
      const els = [...modal.querySelectorAll(sel)].filter(el => el.offsetParent);
      if (!els.length) continue;
      const last   = els[els.length - 1];
      const leaves = [...last.querySelectorAll('*')].filter(el => !el.children.length && el.textContent.trim());
      const txt    = leaves.length ? norm(leaves[leaves.length - 1].textContent) : norm(last.textContent);
      if (txt.length > 5) return txt;
    }
    // Fallback: scan for question-like visible text in the modal
    const all = [...modal.querySelectorAll('span,p,div')].filter(el =>
      el.offsetParent && !el.children.length && el.textContent.trim().length > 10
    );
    for (let i = all.length - 1; i >= 0; i--) {
      const t = norm(all[i].textContent);
      if (t.length > 10 && t.length < 300
          && (/\?$/.test(t) || /(ctc|notice|experience|salary|lakh|joining|current|expected)/i.test(t)))
        return t;
    }
    return '';
  }

  async function fillChatbotStep(modal) {
    if (S.running) return;
    S.running = true;
    await sleep(500);

    const inp      = findChatInput(modal);
    const chips    = findChips(modal);
    const hasInp   = !!(inp?.offsetParent && !inp.disabled && !inp.readOnly);
    const hasChips = chips.length > 0;

    if (!hasInp && !hasChips) { S.running = false; return; }   // bot thinking / transitioning
    if (hasInp && inp.value.trim()) { S.running = false; return; } // already typed
    try {
      const qText = getLastBotMessage(modal);
      const qKey  = qText.slice(0, 80);
      if (!qText || S.answeredQs.has(qKey)) { S.running = false; return; }

      const m = matchQ(qText);

      // Try chips first (MCQ)
      if (hasChips && m?.pickRxs?.length) {
        for (const chip of chips) {
          if (m.pickRxs.some(rx => rx.test(low(chip.textContent.trim())))) {
            await sleep(200);
            chip.click();
            S.answeredQs.add(qKey);
            S.filled++;
            status(`✓ ${m.key}: ${norm(chip.textContent)}`);
            S.running = false; return;
          }
        }
        // Chips present but no pattern matched — wait for Rohit
        status(`? ${qText.slice(0, 60)} — ${chips.length} options, pick manually`);
        S.needs++;
        S.running = false; return;
      }

      // Fill text / number input
      if (hasInp) {
        if (!m) {
          status(`? No match: ${qText.slice(0, 60)}`);
          S.needs++;
          S.running = false; return;
        }
        const isNum = inp.type === 'number' || inp.inputMode === 'numeric' || inp.inputMode === 'decimal';
        const val   = isNum ? m.value.replace(/[^\d.]/g, '') : m.value;
        if (!val) { S.needs++; S.running = false; return; }

        inp.focus();
        await sleep(100);
        setVal(inp, val);
        await sleep(300);

        const btn = findSendBtn(modal);
        if (btn) {
          btn.click();
        } else {
          inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true, composed: true }));
          inp.dispatchEvent(new KeyboardEvent('keyup',   { key: 'Enter', keyCode: 13, bubbles: true }));
        }

        S.answeredQs.add(qKey);
        S.filled++;
        status(`✓ ${m.key}: ${val}`);
      }
    } catch (e) { console.warn('[NaukriFill chatbot]', e); }
    S.running = false;
  }

  function startChatObs(modal) {
    if (S.chatObs) S.chatObs.disconnect();
    let timer = null;
    S.chatObs = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(() => fillChatbotStep(modal), 900);
    });
    S.chatObs.observe(modal, { childList: true, subtree: true, characterData: true });
    setTimeout(() => fillChatbotStep(modal), 1000);
  }

  // ── Modal detection ──────────────────────────────────────────────────────
  function isChatbot(el) {
    const src = (el.className || '').toLowerCase() + (el.innerHTML || '').slice(0, 400).toLowerCase();
    return /chatbot|chat[_-]?window|chat[_-]?body|ssrc[_-]?.*(receive|send)|bot[_-]?message|receive[_-]?message/.test(src);
  }

  const MODAL_SELS = [
    '.chatbot_modal', '[class*="chatbot_modal"]', '[class*="chatbotModal"]',
    '[class*="apply-modal"]', '[class*="applyModal"]', '[class*="apply_modal"]',
    '[class*="easyApply"]',   '[class*="easy-apply"]',
    '[class*="quick-apply"]', '[class*="quickApply"]',
    '[class*="apply-popup"]', '[class*="applyPopup"]',
    '.apply-message', '.bot-container',
    '[role="dialog"][class*="apply"]',
  ];

  function findModal() {
    for (const sel of MODAL_SELS) {
      try {
        const el = document.querySelector(sel);
        if (el?.offsetParent) return el;
      } catch {}
    }
    // Fallback: any visible dialog/overlay mentioning CTC or notice
    for (const d of document.querySelectorAll('[role="dialog"],[class*="modal"],[class*="overlay"],[class*="popup"]')) {
      if (!d.offsetParent) continue;
      if (/current\s*ctc|expected\s*ctc|notice\s*period|quick\s*apply|easy\s*apply/i.test(d.textContent)) return d;
    }
    return null;
  }

  // ── Main entry ──────────────────────────────────────────────────────────
  async function detectAndFill(force = false) {
    const modal = findModal();
    if (!modal) return;
    if (!force && modal === S.modalEl) return;
    S.modalEl = modal;
    S.filled = 0; S.needs = 0;

    await loadCtx();
    initPanel();
    renderPanel('Detecting…');

    if (isChatbot(modal)) {
      status('Chatbot flow — filling…');
      startChatObs(modal);
    } else {
      status('Form detected — filling…');
      const r = await fillQuickForm(modal);
      status(`Done: ${r.filled} filled, ${r.needs} need attention`);
    }
  }

  // ── Page-level MutationObserver (waits for modal to appear) ─────────────
  const pageObs = new MutationObserver(() => {
    clearTimeout(S.pageTimer);
    S.pageTimer = setTimeout(() => {
      const m = findModal();
      if (m && m !== S.modalEl) detectAndFill();
    }, 500);
  });
  pageObs.observe(document.body || document.documentElement, { childList: true, subtree: true });

  // Manual trigger from popup button (refill) or DevTools console
  window.addEventListener('message', e => {
    if (e.source === window && e.data?.naukrifill === 'refill') detectAndFill(true);
  });

  // Initial check in case the modal is already open when the script loads
  setTimeout(() => detectAndFill(), 1500);
})();

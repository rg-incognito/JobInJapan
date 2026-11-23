// JobFill content script: fills job-application forms from Rohit's profile + answer bank.
// Rules: ticks only plain acknowledgement boxes (rules marked "ack": read/acknowledged the privacy notice etc.),
// never marketing / talent-pool / recording / legal-declaration boxes, never clicks submit, never overwrites
// what the user typed. Learns: answers Rohit types or picks himself are sent to the server (/learn) and reused.
(() => {
  if (window.__jobfillLoaded) return;
  window.__jobfillLoaded = true;

  const S = { ctx: null, offline: false, status: new WeakMap(), results: new WeakMap(), running: false, again: false, runs: 0,
              report: null, host: null, panel: null, auto: true, intendedPhone: null, phoneEl: null,
              touched: [], touchedLabels: new Set(), learned: new Map(), learnT: null, userLabels: new Set() };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const norm = (s) => (s || "").replace(/[ \s]+/g, " ").replace(/[*✱]/g, "").trim();
  const low = (s) => norm(s).toLowerCase();
  const rx = (s) => { try { return s ? new RegExp(s, "i") : null; } catch (e) { return null; } };

  // ---------------------------------------------------------------- DOM helpers (open shadow roots too)
  function allEls(root = document) {
    const out = [], stack = [root];
    while (stack.length) {
      const r = stack.pop();
      for (const e of r.querySelectorAll("*")) {
        if (e === S.host) continue;
        out.push(e);
        if (e.shadowRoot) stack.push(e.shadowRoot);
      }
    }
    return out;
  }
  const parentOf = (e) => e.parentElement || (e.getRootNode && e.getRootNode().host) || null;
  function visible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== "hidden" && cs.display !== "none" && cs.opacity !== "0";
  }
  function visibleish(el) {
    if (visible(el)) return true;
    // react-select shrinks / hides its input once a value is chosen: the visible control is what counts
    if (el.tagName === "INPUT" && isCombo(el)) {
      const c = el.closest("[class*=control]");
      if (c && c !== el && visible(c)) return true;
    }
    // custom-styled radios / checkboxes / file inputs are often hidden behind a visible wrapper or label
    if (["radio", "checkbox", "file"].includes(el.type)) {
      const lab = el.labels && el.labels[0];
      if (lab && visible(lab)) return true;
      let p = parentOf(el);
      for (let i = 0; p && i < 3; i++, p = parentOf(p)) if (visible(p)) return true;
    }
    return false;
  }
  const EXCLUDE_TEXT = "select,option,textarea,button,script,style,noscript,[role=listbox],[role=option],[class*=placeholder],[class*=single-value],[class*=multi-value],[aria-live]";
  function ownText(a, members) {
    const memberLabels = new Set();
    for (const m of members) if (m.labels) for (const l of m.labels) memberLabels.add(l);
    const parts = [];
    const w = document.createTreeWalker(a, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      const p = n.parentElement;
      if (!p || p.closest(EXCLUDE_TEXT)) continue;
      const lab = p.closest("label");
      if (lab && (memberLabels.has(lab) || members.some((m) => lab.contains(m)))) continue;
      const t = norm(n.textContent);
      if (t) parts.push(t);
    }
    return norm(parts.join(" "));
  }
  // question text: walk up until an ancestor has text but no foreign form controls
  function questionText(el, members = [el]) {
    const set = new Set(members);
    let a = parentOf(el);
    for (let i = 0; a && i < 7; i++, a = parentOf(a)) {
      if (a === document.body || a === document.documentElement) break;
      const foreign = [...a.querySelectorAll("input:not([type=hidden]),select,textarea")]
        .filter((c) => !set.has(c) && visibleish(c));
      if (foreign.length) break;
      const t = ownText(a, members);
      if (t) return t.slice(0, 400);
    }
    return "";
  }
  function labelOf(el, members) {
    const root = el.getRootNode();
    const lb = el.getAttribute("aria-labelledby");
    if (lb) {
      const t = lb.split(/\s+/).map((id) => (root.getElementById ? root.getElementById(id) : null) || document.getElementById(id))
        .filter(Boolean).map((x) => x.innerText || x.textContent).join(" ");
      if (norm(t) && !members) return norm(t);
    }
    if (!members && el.labels && el.labels.length) {
      const t = [...el.labels].map((l) => ownText(l, [])).join(" ");   // excludes <option> text of wrapped selects
      if (norm(t)) return norm(t);
    }
    const al = el.getAttribute("aria-label");
    if (norm(al) && !members) return norm(al);
    const q = questionText(el, members || [el]);
    if (q) return q;
    return norm(el.getAttribute("placeholder") || el.getAttribute("aria-label") || el.name || el.id || "");
  }
  // smallest element holding every option of a radio / checkbox group, then its question wrapper
  function groupQuestion(members) {
    let b = members[0].parentElement;
    while (b && !members.every((m) => b.contains(m))) b = b.parentElement;
    return b && (b.closest("fieldset") || b.parentElement || b);
  }
  function titleRequired(t) {
    if (!t) return false;
    if (/required/i.test(t.className || "") || /\*\s*$/.test(t.textContent || "")) return true;
    try { return /\*/.test(getComputedStyle(t, "::after").content || "") || /\*/.test(getComputedStyle(t, "::before").content || ""); } catch { return false; }
  }
  function isRequired(el, label, members) {
    if (el.required || el.getAttribute("aria-required") === "true") return true;
    if (members && members.length > 1) {
      if (members.some((m) => m.required || m.getAttribute("aria-required") === "true")) return true;
      const q = groupQuestion(members);
      if (q && q.getAttribute("aria-required") === "true") return true;
      // the question title: first label/legend in the wrapper that is not an option's own label
      const t = q && [...q.querySelectorAll("legend, label, [class*=title], [class*=question]")]
        .find((x) => !x.querySelector("input") && !members.some((m) => x.contains(m) || (m.labels && [...m.labels].includes(x))));
      if (titleRequired(t)) return true;
    }
    const c = el.closest("[class*=required], [data-required=true]");
    if (c) return true;
    const p = parentOf(el), pp = p && parentOf(p);
    return /\*/.test((pp || p || el).textContent || "") && /\*/.test(label || "") ;
  }
  const attrsOf = (el) => ["name", "id", "autocomplete", "data-automation-id", "data-qa", "data-testid"]
    .map((a) => (el.getAttribute(a) || "").toLowerCase()).filter(Boolean);

  // ---------------------------------------------------------------- events
  function fire(el, type) { el.dispatchEvent(new Event(type, { bubbles: true, composed: true })); }
  function key(el, k) {
    const code = { ArrowDown: 40, Enter: 13, Escape: 27, Tab: 9 }[k] || 0;
    for (const t of ["keydown", "keyup"])
      el.dispatchEvent(new KeyboardEvent(t, { key: k, code: k, keyCode: code, which: code, bubbles: true, composed: true }));
  }
  function setText(el, v, blur = true) {
    el.focus();
    el.value = v;              // isolated world -> native setter, so React/Vue value trackers see a change
    fire(el, "input");
    fire(el, "change");
    if (blur) { el.blur(); fire(el, "focusout"); }
  }
  function clickEl(o) {
    for (const t of ["pointerdown", "mousedown", "pointerup", "mouseup"])
      o.dispatchEvent(new MouseEvent(t, { bubbles: true, composed: true, button: 0 }));
    o.click();
  }

  // ---------------------------------------------------------------- matching
  const AC = { "given-name": "first_name", "family-name": "last_name", name: "full_name", email: "email", tel: "phone",
    "tel-national": "phone", "address-level2": "city", "country-name": "country", country: "country",
    organization: "current_company", "organization-title": "current_title", "postal-code": "postal", "address-level1": "state" };
  // [key, label regex (short labels only), attribute regex]
  const KEYS = [
    ["preferred_name", /preferred (first )?name|nickname|name you (go|prefer)/, /preferred.?name/],
    ["first_name", /\b(first|given|fore)\s*name\b|^name \(first\)/, /first.?name|given.?name|^fname$/],
    ["last_name", /\b(last|family)\s*name\b|surname/, /last.?name|family.?name|surname|^lname$/],
    ["email", /e-?mail/, /e-?mail/],
    ["phone_country", /country code|dial(ing)? code|phone country/, /country.?code|phone.?country|dial.?code/],
    ["phone", /phone|mobile|telephone|\bcell\b/, /phone|mobile|^tel$/],
    ["linkedin", /linked\s*in/, /linkedin/],
    ["github", /git\s*hub/, /github/],
    ["leetcode", /leetcode/, /leetcode/],
    ["twitter", /twitter|\bx\.com\b/, /twitter/],
    ["website", /website|portfolio|personal (site|url|page)|\bblog\b|other (url|link|website)|^urls?$|^links?$/, /website|portfolio|urls\[other/],
    ["full_name", /^(full |legal |your |candidate )?name$|full\s*name|legal name/, /^(full.?)?name$|full.?name|candidate.?name|_systemfield_name/],
    ["current_company", /current (company|employer)|^company$|company name|^employer$|present employer|most recent (employer|company)|most recently work/, /^org$|current.?company|^company$|employer/],
    ["current_title", /current (job )?(title|role|position)|^title$|job title|most recent (title|role)/, /^title$|job.?title|current.?title/],
    ["edu_start_month", /start (date )?month/, /start.?(date.?)?month/],
    ["edu_start_year", /start (date )?year/, /start.?(date.?)?year/],
    ["edu_end_month", /end (date )?month/, /end.?(date.?)?month/],
    ["edu_end_year", /end (date )?year/, /end.?(date.?)?year/],
    ["city", /\bcity\b|\btown\b/, /(?<!ethni)city/],
    ["location", /(?<!re)location|^address|current address|where are you (based|located)/, /(?<!re)location|address/],
    ["state", /^state\b|province|^region/, /^state$|province/],
    ["country", /country/, /country/],
    ["postal", /zip|postal|post code|pin ?code/, /zip|postal/],
    ["school", /school|university|college|institution/, /school|university|college/],
    ["degree", /degree/, /degree/],
    ["discipline", /discipline|field of study|major|speciali[sz]ation/, /discipline|major/],
  ];
  function nearPhone(el) {
    let a = parentOf(el);
    for (let i = 0; a && i < 4; i++, a = parentOf(a))
      if (a.querySelector && a.querySelector("input[type=tel],input[id*=phone i],input[name*=phone i],input[autocomplete^=tel]")) return true;
    return false;
  }
  // education block: a wrapper named "education", or a nearby school / degree field (Greenhouse: school--0, degree--0)
  const inEducation = (el) => {
    if (el.closest("[id*=education i],[class*=education i],[data-qa*=education i],[aria-label*=education i]")) return true;
    let a = el.parentElement;
    for (let i = 0; a && i < 6; i++, a = a.parentElement)
      if (a.querySelector("[id^=school i],[id^=degree i],[name*=school i],[name*=degree i],[id*=--school i],[id*=--degree i]")) return true;
    // bare "Start date month/year" on a form that has a school field is the education block (job start dates are asked as text)
    return !!document.querySelector("[id^=school i],[name*=school i],[id*=--school i]") && /^(start|end) date (month|year)$|^(start|end) (month|year)$/.test(low(labelOf(el) || ""));
  };

  function keyFor(el, label) {
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase().split(/\s+/).pop();
    let k = AC[ac] || null;
    const l = low(label);
    if (!k && l.length <= 60) for (const [kk, lr] of KEYS) if (lr.test(l)) { k = kk; break; }
    if (!k) {
      const attrs = attrsOf(el);
      for (const [kk, , ar] of KEYS) if (attrs.some((a) => ar.test(a))) { k = kk; break; }
    }
    if (k === "country" && nearPhone(el) && el.type !== "tel") k = "phone_country";
    if (k && k.startsWith("edu_") && !inEducation(el)) k = null;
    return k;
  }

  const P = () => S.ctx.profile;
  function keyValue(k) {
    const p = P(), e = p.education || {};
    const city = [/^pune,? ?(maharashtra|mh|india)/, /^pune\b/, /^india\b/];
    const V = {
      first_name: { a: p.first_name }, last_name: { a: p.last_name }, preferred_name: { a: p.preferred_name },
      full_name: { a: p.legal_name }, email: { a: p.email },
      phone_country: { a: "India", type: "India", pick: [/^india\b.*91/, /^\+?91\b/, /^india\b/, /\bindia\b/] },
      linkedin: { a: p.linkedin }, github: { a: p.github }, leetcode: { a: p.leetcode }, website: { a: p.github },
      current_company: { a: p.current_employer }, current_title: { a: p.current_title },
      city: { a: p.city, type: p.city, pick: city }, location: { a: p.location, type: p.city, pick: city },
      state: { a: p.state, pick: [/^maharashtra/] }, country: { a: p.country, type: p.country, pick: [/^india\b/] },
      school: { a: e.school, type: e.school_short, types: [e.school_short, "Other"], pick: [/raisoni/, /^other$/] },
      degree: { a: e.degree, pick: [/bachelor.{0,25}(tech|engineer)/, /^bachelor/, /b\.?\s?tech/] },
      discipline: { a: e.discipline, type: e.discipline, pick: [/^computer engineering/] },
      edu_start_month: { a: e.start_month, pick: [/^aug/, /^0?8$/] }, edu_end_month: { a: e.end_month, pick: [/^jun/, /^0?6$/] },
      edu_start_year: { a: String(e.start_year), pick: [new RegExp("^" + e.start_year)] },
      edu_end_year: { a: String(e.end_year), pick: [new RegExp("^" + e.end_year)] },
    };
    const v = V[k];
    return v && v.a ? v : null;
  }

  function resolve(str) {
    if (!str) return str;
    const p = P(), c = S.ctx;
    const map = {
      salary_ask: c.salary_ask || "", salary_currency: (c.salary_ask || "").split(" ")[0] || "",
      current_ctc: p.current_ctc_text || "", notice: p.notice_text || "", dob: p.date_of_birth || "",
      cover_letter: c.cover ? c.cover.text : "", why_country: c.why_country || "",
      reason_looking_now_script: p.reason_looking_now_script || "", reason_left_dmg_script: p.reason_left_dmg_script || "",
      job_city: ((c.job && c.job.location) || "").split(/[,;/(]/)[0].trim(), current_employer: p.current_employer || "",
      job_country: c.country || "",
      // every place named in the job location, in order: "Cardiff, London or Remote (UK)" -> cardiff||london||uk
      job_places: ((c.job && c.job.location) || "").split(/[,;/()]|\bor\b|\band\b/i).map((x) => x.trim().toLowerCase())
        .filter((x) => x && !/^(remote|hybrid|on-?site|office)$/.test(x))
        .map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("||"),
    };
    let missing = false;
    const out = str.replace(/\{(\w+)\}/g, (_, k) => { const v = map[k] ?? p[k] ?? ""; if (!v) missing = true; return v; });
    return missing ? null : out;
  }
  function ruleFor(label, rules, { neverOnly = false, skipNever = false } = {}) {
    const l = low(label);
    if (!l) return null;
    for (const r of rules) {
      if (neverOnly && !r.never) continue;
      if (skipNever && r.never) continue;
      const q = rx(r.q);
      if (q && q.test(l) && !(r.not && rx(r.not) && rx(r.not).test(l))) return r;
    }
    return null;
  }
  function ruleValue(r) {
    if (r.never) return { never: true, rule: r.id || r.q };
    const a = r.a === "" ? "" : resolve(r.a);
    if (a === null) return { unresolved: true, rule: r.id || r.q };
    const pick = r.pick ? resolve(r.pick) : null;
    if (r.pick && !pick) return { unresolved: true, rule: r.id || r.q };
    return { a, pick: pick ? pick.split("||").map(rx).filter(Boolean) : [], avoid: rx(r.avoid), choiceOnly: !!r.choice_only,
             types: r.type ? r.type.split("|") : null, rule: r.id || "custom" };
  }

  function choose(texts, pick = [], a = "", avoid = null) {
    const c = texts.map((t, i) => ({ t: low(t), i }))
      .filter((o) => o.t && !/^(select|choose|please select|--|—|-)\b/.test(o.t) && !(avoid && avoid.test(o.t)));
    for (const p of pick) { const m = c.find((o) => p.test(o.t)); if (m) return m.i; }
    const al = low(a);
    if (al) {
      const m = c.find((o) => o.t === al) || c.find((o) => o.t.startsWith(al)) || (al.length > 3 && c.find((o) => o.t.includes(al)));
      if (m) return m.i;
    }
    return -1;
  }

  // ---------------------------------------------------------------- widget fillers
  function isCombo(el) {
    return el.getAttribute("role") === "combobox" || el.getAttribute("aria-autocomplete") === "list" ||
      /select__input|react-select/.test(el.className + " " + el.id);
  }
  // the element that holds a combobox's input, its chosen value and (often) its menu.
  // Not the input itself and not react-select's inner "input-container" / "value-container".
  function comboBox(el) {
    const ctl = el.closest("[class*=control]");
    if (ctl && ctl !== el && ctl.parentElement) return ctl.parentElement;
    return el.closest("[class*=select__container],[class*=select-container],[class*=container]:not([class*=input-container]):not([class*=value-container])") || parentOf(el) || el;
  }
  function comboHasValue(el) {
    const box = comboBox(el);
    const sv = box && box.querySelector("[class*=single-value],[class*=multi-value]");
    if (sv && norm(sv.textContent)) return true;
    return !!(el.value && !el.getAttribute("aria-activedescendant") && !/select__input/.test(el.className) && !box.querySelector("[class*=select__]"));
  }
  function optionEls(el) {
    const ids = [el.getAttribute("aria-controls"), el.getAttribute("aria-owns")].filter(Boolean);
    const root = el.getRootNode();
    let opts = [];
    for (const id of ids) {
      const lb = (root.getElementById && root.getElementById(id)) || document.getElementById(id);
      if (lb) opts.push(...lb.querySelectorAll("[role=option],[class*=option]"));
    }
    const sel = "[role=option],[id*=-option-],.select__option,[class*=menu] [class*=option],.dropdown-results > div,.pac-item,[class*=suggestion]";
    if (!opts.length) {
      // the combobox's own menu first: walk up until the ancestor would also hold another combobox.
      // (A phone-code list left in the page must never answer a different question.)
      let a = parentOf(el);
      for (let k = 0; a && k < 6; k++, a = parentOf(a)) {
        const others = [...a.querySelectorAll("input[role=combobox],[role=combobox]")].filter((x) => x !== el && !x.contains(el));
        if (others.length) break;
        const mine = [...a.querySelectorAll(sel)].filter((o) => visible(o));
        if (mine.length) { opts = mine; break; }
      }
    }
    if (!opts.length) {
      opts = [...(root.querySelectorAll ? root.querySelectorAll(sel) : [])];
      if (!opts.length && root !== document) opts = [...document.querySelectorAll(sel)];
      // drop options that visibly belong to another combobox (react-select ids name their input; phone-code lists)
      const foreign = (o) => {
        const m = /^react-select-(.+?)-option-/.exec(o.id || "");
        if (m && m[1] !== el.id && document.getElementById(m[1])) return true;   // names a different, real input
        return !!o.closest(".iti, .iti__country-list, [class*=phone]") && !el.closest(".iti, [class*=phone]");
      };
      opts = opts.filter((o) => !foreign(o));
    }
    return [...new Set(opts)].filter((o) => visible(o) && norm(o.textContent) &&
      !/^(loading|searching|no (options|results)|type to search)/i.test(norm(o.textContent)) &&
      !o.querySelector("[role=option],[id*=-option-]"));
  }
  async function waitOptions(el, ms) {
    const t0 = Date.now(); let last = -1, opts = [];
    while (Date.now() - t0 < ms) {
      await sleep(150);
      opts = optionEls(el);
      if (opts.length && opts.length === last) return opts;
      last = opts.length;
    }
    return opts;
  }
  async function fillCombo(el, v) {
    if (comboHasValue(el)) {
      const box = comboBox(el);
      if (box && /\+\s?91\b/.test(box.textContent)) S.hasPhoneCountry = true;
      return { status: "kept" };
    }
    const typed = v.type || v.a;
    el.focus(); clickEl(el);
    let opts = [];
    if (!v.type) {
      key(el, "ArrowDown"); opts = await waitOptions(el, 900);
      if (!opts.length) {
        // react-select and friends open on a mouse-down on the control, not on keys or a click on the input
        const ctl = el.closest("[class*=control]") || parentOf(el) || el;
        for (const t of ["pointerdown", "mousedown"]) ctl.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, button: 0 }));
        ctl.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, button: 0 }));
        opts = await waitOptions(el, 1200);
      }
    }
    const firstSeen = opts.slice(0, 20).map((o) => norm(o.textContent));
    let i = choose(opts.map((o) => o.textContent), v.pick, v.a, v.avoid);
    // menu never opened and nothing to search for: typing won't help (and costs seconds per field)
    const menuOpened = firstSeen.length > 0 || v.type || v.types;
    for (const t of (i < 0 && menuOpened ? (v.types || [typed]) : []).filter(Boolean)) {
      setText(el, t, false);
      opts = await waitOptions(el, 4000);
      i = choose(opts.map((o) => o.textContent), v.pick, v.a, v.avoid);
      if (i >= 0) break;
    }
    if (i < 0) {
      const seen = firstSeen.length ? firstSeen : opts.slice(0, 20).map((o) => norm(o.textContent));
      if (el.value && S.status.get(el) !== "filled") setText(el, "", false);
      key(el, "Escape"); el.blur();
      return { status: "needs", options: seen };
    }
    const chosen = norm(opts[i].textContent);
    const optTexts = opts.slice(0, 12).map((o) => norm(o.textContent));
    if (/\+\s?91\b/.test(chosen)) S.hasPhoneCountry = true;
    clickEl(opts[i]);
    await sleep(300);
    if (!comboHasValue(el) && document.activeElement === el) { key(el, "Enter"); await sleep(200); }
    el.blur();
    return { status: "filled", value: chosen, options: optTexts };
  }
  function fillSelect(el, v) {
    if (el.value && el.selectedIndex > 0 && !/^(select|choose|please|--)/i.test(norm(el.options[el.selectedIndex].text)))
      return { status: "kept" };
    const opts = [...el.options];
    const i = choose(opts.map((o) => o.text), v.pick, v.a, v.avoid);
    if (i < 0) return { status: "needs", options: opts.map((o) => norm(o.text)).filter(Boolean).slice(0, 25) };
    el.value = opts[i].value; fire(el, "input"); fire(el, "change");
    if (/\+\s?91\b/.test(opts[i].text)) S.hasPhoneCountry = true;
    return { status: "filled", value: norm(opts[i].text), options: opts.slice(0, 12).map((o) => norm(o.text)) };
  }
  const optLabel = (r) => norm((r.labels && r.labels[0] && r.labels[0].textContent) || r.getAttribute("aria-label") ||
    (parentOf(r) && parentOf(r).textContent) || r.value);
  function fillRadios(group, v) {
    if (group.some((r) => r.checked)) return { status: "kept" };
    const texts = group.map(optLabel);
    const i = choose(texts, v.pick, v.a, v.avoid);
    if (i < 0) return { status: "needs", options: texts };
    const r = group[i];
    if (visible(r)) r.click(); else ((r.labels && r.labels[0]) || r).click();
    if (!r.checked) { r.checked = true; fire(r, "change"); }
    return { status: "filled", value: texts[i], options: texts };
  }
  function fillButtons(btns, v) {
    if (btns.some((b) => b.getAttribute("aria-pressed") === "true" || b.getAttribute("aria-checked") === "true" || /selected|active|checked/i.test(b.className))) return { status: "kept" };
    const texts = btns.map((b) => b.textContent);
    const i = choose(texts, v.pick, v.a, v.avoid);
    if (i < 0) return { status: "needs", options: texts.map(norm) };
    clickEl(btns[i]);
    return { status: "filled", value: norm(texts[i]) };
  }
  function b64ToFile(f) {
    const bin = atob(f.b64), u = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    return new File([u], f.name, { type: f.type });
  }
  function fillFile(el, f) {
    if (el.files && el.files.length) return { status: "kept" };
    const dt = new DataTransfer();
    dt.items.add(b64ToFile(f));
    el.files = dt.files;
    fire(el, "input"); fire(el, "change");
    return { status: "filled", value: f.name };
  }
  function digits(s) { return (s || "").replace(/[^\d]/g, ""); }
  // ---- dates
  function isDatePicker(el) {
    if ((el.type || "").toLowerCase() === "date") return true;
    const t = low([el.placeholder, el.getAttribute("aria-label"), el.className, el.name, el.id, el.getAttribute("data-testid")].join(" "));
    return /pick (a )?date|select (a )?date|choose (a )?date|dd ?[\/.-] ?mm|mm ?[\/.-] ?dd|yyyy|date.?picker|datepicker/.test(t);
  }
  const pad = (n) => String(n).padStart(2, "0");
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  function dateFor(a, ruleId, label) {
    if (ruleId === "notice" || /start|join|available|availability|notice/.test(low(label))) {
      const days = (P().notice_period_days || 60) + 1;
      return new Date(Date.now() + days * 864e5);
    }
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(a || "");
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  }
  function dateFormats(el, d) {
    const ph = low(el.placeholder || "");
    const us = `${pad(d.getMonth() + 1)}/${pad(d.getDate())}/${d.getFullYear()}`, eu = `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
    if (/dd ?[\/.-] ?mm/.test(ph)) return [eu, iso(d)];
    if (/mm ?[\/.-] ?dd/.test(ph)) return [us, iso(d)];
    return [us, iso(d), eu];
  }
  function textValue(el, a, ruleId) {
    const t = (el.type || "").toLowerCase();
    if (t === "number" || el.inputMode === "numeric") {
      const d = digits(a.replace(/,(\d{2}),/, "$1"));
      return d || null;
    }
    if (t === "date") {
      if (ruleId === "notice") { const d = new Date(Date.now() + 60 * 864e5); return d.toISOString().slice(0, 10); }
      return /^\d{4}-\d{2}-\d{2}$/.test(a) ? a : null;
    }
    if (t === "url" && !/^https?:/.test(a)) return null;
    if (t === "email" && !/@/.test(a)) return null;
    const max = el.maxLength > 0 ? el.maxLength : 0;
    if (max && a.length > max) return null;
    return a;
  }

  // ---------------------------------------------------------------- collection
  function collect() {
    const fields = [], radios = new Map(), seenBtn = new Set();
    for (const el of allEls()) {
      const tag = el.tagName;
      if (tag === "INPUT") {
        const t = (el.type || "text").toLowerCase();
        if (["hidden", "submit", "button", "reset", "image", "password", "search"].includes(t) || el.disabled || el.readOnly && !isCombo(el)) continue;
        if (!visibleish(el)) continue;
        if (t === "radio") {
          const k = (el.name || "") + "|" + (el.name ? "" : (el.closest("fieldset,[role=radiogroup]") || parentOf(parentOf(el)) || {}).id);
          const rootKey = el.getRootNode();
          if (!radios.has(rootKey)) radios.set(rootKey, new Map());
          const m = radios.get(rootKey);
          if (!m.has(k)) m.set(k, []);
          m.get(k).push(el);
        } else if (t === "checkbox") fields.push({ kind: "checkbox", el });
        else if (t === "file") fields.push({ kind: "file", el });
        else if (isCombo(el)) fields.push({ kind: "combo", el });
        else fields.push({ kind: "text", el });
      } else if (tag === "TEXTAREA") {
        if (!el.disabled && visible(el)) fields.push({ kind: "text", el });
      } else if (tag === "SELECT") {
        if (!el.disabled && visibleish(el)) fields.push({ kind: "select", el });
      } else if (tag === "BUTTON" && /^yes$/i.test(norm(el.textContent)) && el.getAttribute("type") !== "submit" && !seenBtn.has(el)) {
        // yes / no button groups (Ashby and others). Real submit buttons never read "Yes"/"No".
        const box = parentOf(el);
        const btns = box ? [...box.querySelectorAll("button")].filter((b) => b.getAttribute("type") !== "submit" && /^(yes|no)$/i.test(norm(b.textContent))) : [];
        if (btns.length === 2 && visible(el)) { btns.forEach((b) => seenBtn.add(b)); fields.push({ kind: "buttons", el: box, btns }); }
      }
    }
    for (const m of radios.values()) for (const g of m.values()) fields.push({ kind: "radio", el: g[0], group: g });
    // checkbox groups (same name, several boxes) are multi-choice questions: treat as one item
    const byName = new Map();
    for (const f of fields.filter((f) => f.kind === "checkbox" && f.el.name)) {
      const k = f.el.name; if (!byName.has(k)) byName.set(k, []); byName.get(k).push(f);
    }
    for (const g of byName.values()) if (g.length > 1) { g[0].kind = "checkgroup"; g[0].group = g.map((x) => x.el); g.slice(1).forEach((x) => (x.skip = true)); }
    // hidden checkbox that backs a yes/no button group belongs to that question: skip it
    const boxes = fields.filter((f) => f.kind === "buttons").map((f) => parentOf(f.el) || f.el);
    for (const f of fields) {
      const i = boxes.findIndex((b) => f.kind === "checkbox" && b.contains(f.el));
      if (i >= 0) { f.skip = true; }
    }
    for (const f of fields) if (f.kind === "buttons") {
      const q = parentOf(f.el) || f.el;
      f.members = [...f.btns, ...q.querySelectorAll("input[type=checkbox],input[type=hidden]")];
    }
    // "Autofill from resume" uploaders would overwrite our values with the site's resume parse
    for (const f of fields) if (f.kind === "file" && /autofill/i.test(questionText(f.el))) f.skip = true;
    return fields.filter((f) => !f.skip);
  }

  // ---------------------------------------------------------------- one field
  const CHOICE = new Set(["checkbox", "checkgroup", "radio", "select", "combo", "buttons"]);
  async function handle(f) {
    const { el, kind } = f;
    const members = f.group || (f.btns ? f.btns : null);
    const label = kind === "buttons" ? questionText(f.btns[0], f.members || f.btns) : labelOf(el, kind === "radio" || kind === "checkgroup" ? members : null);
    const required = isRequired(el, label, kind === "radio" || kind === "checkgroup" ? members : null);
    const base = { label: label.slice(0, 200), kind, required };
    const allRules = S.ctx.rules || [], appRules = S.ctx.app_rules || [];
    const rules = allRules.filter((r) => !r.ack), ackRules = allRules.filter((r) => r.ack);
    const learnedRules = S.ctx.learned_rules || [];

    if (kind === "file") {
      const t = low(label + " " + attrsOf(el).join(" ") + " " + (el.accept || ""));
      let which = /cover/.test(t) ? "cover" : /resume|\bcv\b|curriculum|résumé/.test(t) ? "resume" : null;
      if (!which && collect.fileCount === 1) which = "resume";
      const f2 = which === "cover" ? S.ctx.cover : which === "resume" ? S.ctx.resume : null;
      if (!f2) return { ...base, status: which === "cover" && !required ? "optional" : "needs", key: which || "file" };
      return { ...base, key: which, ...fillFile(el, f2) };
    }

    let v = null, key = null, ruleId = null;
    const isChoice = CHOICE.has(kind);
    // plain acknowledgements ("I have read the privacy notice", "Acknowledge/Confirm"): Rohit wants these ticked
    if (isChoice && kind !== "checkgroup") {
      // "required_only" ack rules (the mandatory data-processing consent) apply only when the form won't submit without them
      const ak = ruleFor(label, ackRules.filter((r) => (!r.required_only || required) && !(r.no_checkbox && kind === "checkbox")));
      if (ak) {
        if (kind === "checkbox") {
          if (el.checked) return { ...base, key: "ack", status: "acked", value: "ticked" };
          el.click();
          if (!el.checked) ((el.labels && el.labels[0]) || el).click();
          if (!el.checked) { el.checked = true; fire(el, "change"); }
          return { ...base, key: "ack", status: el.checked ? "acked" : "consent", value: "ticked" };
        }
        const av = ruleValue(ak);
        const r = kind === "select" ? fillSelect(el, av) : kind === "combo" ? await fillCombo(el, av)
          : kind === "radio" ? fillRadios(f.group, av) : fillButtons(f.btns, av);
        return { ...base, key: "ack", ...r, status: r.status === "filled" || r.status === "kept" ? "acked" : "consent" };
      }
    }
    if (isChoice) {
      const nr = ruleFor(label, rules, { neverOnly: true });
      if (nr) return { ...base, status: "consent", rule: nr.id };
    }
    const ar = ruleFor(label, appRules);
    if (ar) { v = ruleValue(ar); ruleId = "app"; }
    // answers Rohit gave himself on earlier forms (exact question match) beat the generic bank
    if (!v) { const lr = ruleFor(label, learnedRules); if (lr) { v = ruleValue(lr); ruleId = "learned"; } }
    // long labels are questions: answer-bank rules beat profile keys ("Which office location..." is not "location")
    if (!v && label.length > 40) {
      if (!isChoice && ruleFor(label, rules, { neverOnly: true })) return { ...base, status: "consent" };
      const r = ruleFor(label, rules, { skipNever: true });
      if (r) { v = ruleValue(r); ruleId = r.id; }
    }
    if (!v && isChoice) {
      const er = ruleFor(label, rules.filter((r) => /^eeo_/.test(r.id || "")));
      if (er) { v = ruleValue(er); ruleId = er.id; }
    }
    if (!v && kind !== "buttons" && kind !== "radio" && kind !== "checkgroup") {
      key = keyFor(el, label);
      if (key === "phone") {
        if (el.value && S.status.get(el) !== "filled") return { ...base, key, status: "kept" };
        const national = S.hasPhoneCountry;
        const val = national ? P().phone_national : P().phone;
        S.intendedPhone = val; S.phoneEl = el;
        setText(el, val);
        return { ...base, key, status: "filled", value: val };
      }
      if (key) { v = keyValue(key); if (!v) return { ...base, key, status: required ? "needs" : "optional" }; }
    }
    if (!v && !isChoice) {
      const nr = ruleFor(label, rules, { neverOnly: true });
      if (nr) return { ...base, status: "consent", rule: nr.id };
    }
    if (!v) {
      const r = ruleFor(label, rules, { skipNever: true });
      if (r) { v = ruleValue(r); ruleId = r.id; }
    }
    if (!v || v.unresolved) return { ...base, status: required ? "needs" : "optional", rule: v && v.rule };
    if (v.never) return { ...base, status: "consent", rule: v.rule };
    const tag = key || ruleId;

    switch (kind) {
      case "text": {
        if (el.value && S.status.get(el) !== "filled") return { ...base, key: tag, status: "kept" };
        if (v.choiceOnly || v.a === "") return { ...base, key: tag, status: required ? "needs" : "optional" };
        if ((key === "location" || key === "city" || ruleId === "located") && el.tagName === "INPUT") {
          // plain input with a suggestion dropdown (Lever, Workable...): type the city, pick a suggestion if one appears
          setText(el, P().city, false);
          const opts = await waitOptions(el, 2500);
          const i = choose(opts.map((o) => o.textContent), v.pick || [/^pune\b/], v.a);
          if (i >= 0) {
            const chosen = norm(opts[i].textContent);
            clickEl(opts[i]); await sleep(300); el.blur();
            return { ...base, key: tag, status: "filled", value: chosen };
          }
          setText(el, v.a);
          return { ...base, key: tag, status: "filled", value: v.a };
        }
        if (isDatePicker(el)) {
          // date pickers throw away free text ("60 days notice"): give them a real date and check it stuck
          const d = dateFor(v.a, ruleId, label);
          if (!d) return { ...base, key: tag, status: "needs" };
          if ((el.type || "").toLowerCase() === "date") { setText(el, iso(d)); return { ...base, key: tag, status: "filled", value: iso(d) }; }
          for (const s of dateFormats(el, d)) {
            setText(el, s, false); key(el, "Enter"); await sleep(400); key(el, "Escape"); el.blur(); fire(el, "focusout"); await sleep(400);
            if (el.value && /\d/.test(el.value)) return { ...base, key: tag, status: "filled", value: el.value, full: el.value };
          }
          return { ...base, key: tag, status: "needs" };
        }
        const val = textValue(el, v.a, ruleId);
        if (val == null) return { ...base, key: tag, status: "needs" };
        setText(el, val);
        return { ...base, key: tag, status: "filled", value: val.slice(0, 80), full: val };
      }
      case "select": return { ...base, key: tag, ...fillSelect(el, v) };
      case "combo": return { ...base, key: tag, ...(await fillCombo(el, v)) };
      case "radio": return { ...base, key: tag, ...fillRadios(f.group, v) };
      case "buttons": return { ...base, key: tag, ...fillButtons(f.btns, v) };
      case "checkbox": {
        // only tick plain statements of fact we know are true; anything else is Rohit's call
        if (["relocate", "office", "travel", "adult"].includes(ruleId) && !el.checked) {
          el.click(); return { ...base, key: tag, status: "filled", value: "ticked" };
        }
        return { ...base, key: tag, status: el.checked ? "kept" : required ? "needs" : "optional" };
      }
      case "checkgroup": {
        if (f.group.some((c) => c.checked)) return { ...base, key: tag, status: "kept" };
        const texts = f.group.map(optLabel);
        const i = choose(texts, v.pick, v.a, v.avoid);
        if (i < 0) return { ...base, key: tag, status: "needs", options: texts };
        f.group[i].click();
        return { ...base, key: tag, status: "filled", value: texts[i] };
      }
    }
    return { ...base, status: "needs" };
  }

  // ---------------------------------------------------------------- highlight + panel
  const COLORS = { filled: "#16a34a", kept: "#16a34a", acked: "#0d9488", needs: "#d97706", consent: "#9333ea" };
  function mark(f, status) {
    const c = COLORS[status];
    let t = f.kind === "buttons" ? f.el : f.el;
    if (f.kind === "combo") t = f.el.closest("[class*=control]") || f.el;
    if (!visible(t) || f.kind === "radio" || f.kind === "checkbox" || f.kind === "checkgroup" || f.kind === "file") {
      let p = parentOf(t); for (let i = 0; p && i < 3 && !visible(p); i++) p = parentOf(p);
      if (f.kind === "radio" || f.kind === "checkgroup") p = (f.group[0].closest("fieldset,[role=radiogroup]") || parentOf(parentOf(f.group[0])) || p);
      t = p || t;
    }
    if (!t || !t.style) return;
    if (!c) { t.style.removeProperty("outline"); t.style.removeProperty("outline-offset"); return; }
    t.style.setProperty("outline", `2px solid ${c}`, "important");
    t.style.setProperty("outline-offset", "2px", "important");
    f.markEl = t;
  }
  function renderPanel(rep) {
    if (!S.host) {
      S.host = document.createElement("div");
      S.host.id = "__jobfill_panel";
      S.host.style.cssText = "all:initial;position:fixed;right:14px;bottom:14px;z-index:2147483647";
      S.panel = S.host.attachShadow({ mode: "closed" });
      (document.body || document.documentElement).appendChild(S.host);
    }
    const job = S.ctx.job;
    const item = (f, c) => `<li data-i="${f._i}" style="border-left:3px solid ${c}">${esc(f.label || "(unlabelled)")}${f.required ? " *" : ""}</li>`;
    S.panel.innerHTML = `<style>
      .b{font:12px/1.35 system-ui,sans-serif;background:#fff;color:#111;border:1px solid #d1d5db;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.18);width:290px;max-height:60vh;display:flex;flex-direction:column}
      .h{padding:8px 10px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;align-items:center;gap:6px}
      .t{font-weight:700}.s{color:#555;font-size:11px}
      ul{list-style:none;margin:0;padding:6px 8px;overflow:auto}li{padding:3px 6px;margin:3px 0;cursor:pointer;background:#fafafa;border-radius:4px}
      li:hover{background:#f0f0f0}button{font:inherit;border:0;border-radius:5px;padding:3px 8px;cursor:pointer;background:#2563eb;color:#fff}
      .x{background:#e5e7eb;color:#111}.n{font-weight:600;margin:4px 8px 0}.min .bd{display:none}
    </style>
    <div class="b"><div class="h"><div><div class="t">JobFill ${S.offline ? "(offline)" : ""}</div>
      <div class="s">${job ? esc(job.company + " · " + job.title).slice(0, 60) : "no tracked job matched"}</div>
      <div class="s"><b style="color:#16a34a">${rep.filled.length} filled</b> · <b style="color:#d97706">${rep.needs.length} need you</b> · <b style="color:#9333ea">${rep.consent.length} consent</b>${rep.acked.length ? ` · <b style="color:#0d9488">${rep.acked.length} ack ticked</b>` : ""}${S.learnedCount ? ` · learned ${S.learnedCount}` : ""}</div></div>
      <div><button id="r">Refill</button> <button id="x" class="x">–</button></div></div>
      <div class="bd">${rep.needs.length ? `<div class="n">Needs an answer</div><ul>${rep.needs.map((f) => item(f, "#d97706")).join("")}</ul>` : ""}
      ${rep.consent.length ? `<div class="n">Tick yourself</div><ul>${rep.consent.map((f) => item(f, "#9333ea")).join("")}</ul>` : ""}
      ${rep.acked.length ? `<div class="n">Acknowledged for you (check)</div><ul>${rep.acked.map((f) => item(f, "#0d9488")).join("")}</ul>` : ""}
      <div class="s" style="padding:6px 10px">Never submits. Answers you type are learned for next time.</div></div></div>`;
    S.panel.getElementById("r").onclick = () => run({ refresh: true, all: true });
    S.panel.getElementById("x").onclick = () => S.panel.querySelector(".b").classList.toggle("min");
    S.panel.querySelectorAll("li").forEach((li) => (li.onclick = () => {
      const f = S.lastFields[+li.dataset.i]; const t = (f && (f.markEl || f.el));
      if (t) { t.scrollIntoView({ block: "center", behavior: "smooth" }); (f.el.focus && f.el.focus()); }
    }));
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---------------------------------------------------------------- main loop
  function looksLikeApplication(fields) {
    const hasEmail = fields.some((f) => f.kind === "text" && (f.el.type === "email" || /e-?mail/.test(attrsOf(f.el).join(" "))));
    const hasFile = fields.some((f) => f.kind === "file");
    return fields.length >= 3 && (hasEmail || hasFile);
  }
  // After the extension is reloaded/updated, scripts already running in open tabs lose their connection
  // ("Extension context invalidated"). Such an orphan stops quietly and asks for a page refresh.
  const alive = () => { try { return !!(chrome.runtime && chrome.runtime.id); } catch (e) { return false; } };
  function retire() {
    if (S.dead) return;
    S.dead = true;
    try { obs.disconnect(); } catch (e) { /* not started yet */ }
    clearTimeout(S.learnT);
    if (S.panel) {
      S.panel.innerHTML = `<div style="font:12px system-ui,sans-serif;background:#fff;color:#111;border:1px solid #d1d5db;border-radius:10px;padding:10px;width:270px;box-shadow:0 6px 24px rgba(0,0,0,.18)">
        <b>JobFill was updated.</b><br>Refresh this page to use the new version.</div>`;
    }
  }
  async function send(msg) {
    if (S.dead || !alive()) { retire(); return null; }
    try { return await chrome.runtime.sendMessage(msg); }
    catch (e) {
      // only a lost extension context means "updated": other failures (worker restarting, page navigating
      // away mid-message) are transient
      if (!alive() || /context invalidated/i.test(String(e && e.message || e))) { retire(); return null; }
      return null;
    }
  }
  async function getContext() {
    const pageText = (document.title + " " + (document.body ? document.body.innerText.slice(0, 4000) : ""));
    const r = await send({ type: "context", frameUrl: location.href, pageText });
    if (S.dead) throw new Error("retired");
    if (!r || !r.ok) throw new Error((r && r.error) || "no context");
    S.ctx = r.ctx; S.offline = !!r.offline;
  }
  async function run({ refresh = false, all = false, force = false } = {}) {
    if (S.dead) return;
    if (S.running) { S.again = true; return; }
    S.running = true;
    try {
      let fields = collect();
      collect.fileCount = fields.filter((f) => f.kind === "file").length;
      if (!force && !looksLikeApplication(fields)) return;
      if (!S.ctx || refresh) await getContext();
      if (all) for (const f of fields) if (S.status.get(f.el) !== "filled") S.status.delete(f.el);
      S.hasPhoneCountry = fields.some((f) => (f.kind === "combo" || f.kind === "select") && keyFor(f.el, labelOf(f.el)) === "phone_country");
      // country / phone-code pickers first (they can reformat the phone field), then quick fields,
      // then the slow dropdowns, files last
      const rank = (f) => {
        if (f.kind === "file") return 3;
        if (f.kind !== "combo" && f.kind !== "select") return 1;
        return /^(phone_country|country)$/.test(keyFor(f.el, labelOf(f.el)) || "") ? 0 : f.kind === "select" ? 1 : 2;
      };
      fields.sort((a, b) => rank(a) - rank(b));
      for (const f of fields) {
        const prev = S.status.get(f.el);
        if (prev && !all) continue;
        if (prev === "user" || (S.userLabels.size && S.userLabels.has(fieldKey(f)) && currentValue(f))) {
          S.status.set(f.el, "user"); continue;
        }
        let r;
        try { r = await handle(f); } catch (e) { r = { label: labelOf(f.el), kind: f.kind, status: "needs", error: String(e) }; }
        if (r.status === "needs" && !r.required) r.status = "optional";   // "needs" = required and unanswered
        S.results.set(f.el, r);
        S.status.set(f.el, r.status);
        mark(f, r.status);
      }
      // phone formatters (Greenhouse intl input) sometimes rewrite the number after the country is chosen
      if (S.phoneEl && S.intendedPhone) {
        await sleep(400);
        const want = digits(S.intendedPhone), got = digits(S.phoneEl.value);
        if (got !== want && got !== "91" + want) setText(S.phoneEl, S.intendedPhone);
      }
      buildReport(fields);
    } catch (e) {
      if (!S.dead) console.warn("[JobFill]", e);
    } finally {
      S.running = false;
      S.quietUntil = Date.now() + 600;   // late change events from our own last clicks
      if (S.again) { S.again = false; setTimeout(() => run(), 300); }
    }
  }
  // cumulative per question: React re-renders replace elements, so results are kept by label, not by node
  S.byQuestion = new Map();
  function buildReport(fields) {
    S.lastFields = fields;
    fields.forEach((f, i) => {
      const r = S.results.get(f.el); if (!r) return;
      if (!f.markEl && r.status) mark(f, r.status);
      // keyed by question only, so a later "filled"/"kept" result replaces an earlier "needs"
      const k = r.label ? r.label.trim().toLowerCase() : r.kind + "|#" + i;
      S.byQuestion.set(k, { r, i });
    });
    const rep = { filled: [], needs: [], consent: [], acked: [], optional: [] };
    for (const { r, i } of S.byQuestion.values()) {
      const e = { _i: i, label: r.label, kind: r.kind, required: r.required, key: r.key || r.rule || null };
      if (r.value) e.value = r.value;
      if (r.options) e.options = r.options;
      if (r.status === "filled" || r.status === "kept") rep.filled.push(e);
      else if (r.status === "consent") rep.consent.push(e);
      else if (r.status === "acked") rep.acked.push(e);
      else if (r.status === "needs") rep.needs.push(e);
      else rep.optional.push(e);
    }
    S.report = rep;
    document.documentElement.setAttribute("data-jobfill", JSON.stringify({ filled: rep.filled.length, needs: rep.needs.length, consent: rep.consent.length, acked: rep.acked.length }));
    renderPanel(rep);
    send({ type: "report", payload: { job_id: S.ctx.job && S.ctx.job.job_id, url: location.href, report: rep } }).catch(() => {});
    if (S.ctx.autosubmit) scheduleAutoSubmit();
  }

  // ---------------------------------------------------------------- auto-submit (Rohit, 2026-11-02)
  // Only for jobs the autopilot already verified (server sets ctx.autosubmit). Clicks Submit once the form has been
  // stable for 8 s with 0 required questions open, no required consent unticked and the resume attached.
  // A CAPTCHA / emailed code is never touched: the tab simply stays open for Rohit.
  function submitButton() {
    const vis = (b) => b && b.offsetParent !== null && !b.disabled;
    const cands = [...document.querySelectorAll("button, input[type=submit]")].filter(vis);
    return cands.find((b) => b.id === "btn-submit")
      || cands.find((b) => /^submit( (your )?application)?$|^send application$|^apply$/i.test(norm(b.textContent || b.value)))
      || cands.find((b) => b.type === "submit" && /submit|apply/i.test(norm(b.textContent || b.value)));
  }
  const visibleCaptcha = () => [...document.querySelectorAll("iframe[src*='recaptcha'][src*='anchor'], iframe[src*='hcaptcha'], iframe[src*='turnstile'], iframe[title*='challenge' i]")]
    .some((f) => f.offsetWidth > 30 && f.offsetHeight > 30);
  function scheduleAutoSubmit() {
    if (S.autoSubmitted || window.top !== window) return;
    clearTimeout(S.autoT);
    S.autoT = setTimeout(() => {
      const rep = S.report;
      if (!rep || S.running || S.autoSubmitted || !alive()) return;
      const blockers = rep.needs.length + rep.consent.filter((c) => c.required).length;
      const hasResume = rep.filled.some((f) => f.kind === "file");
      const btn = submitButton();
      if (blockers || !hasResume || !btn || visibleCaptcha() || rep.filled.length < 4) {
        console.info("[JobFill] auto-submit waiting", { needs: rep.needs.length, consent: rep.consent.length, hasResume, btn: !!btn });
        return;
      }
      S.autoSubmitted = true;
      if (S.host) S.host.style.display = "none";          // the panel can cover the button
      console.info("[JobFill] auto-submitting (form verified, 0 open questions)");
      btn.scrollIntoView({ block: "center" });
      btn.click();
      watchApplied(120000, true);
      // validation errors or a challenge: show the panel again for Rohit
      setTimeout(() => { if (!S.appliedSent && S.host) S.host.style.display = ""; }, 15000);
    }, 8000);
  }
  function clearMarks() {
    for (const f of S.lastFields || []) mark(f, null);
    if (S.host) { S.host.remove(); S.host = null; }
  }

  // ---------------------------------------------------------------- learning from Rohit
  // Only *trusted* input / key / mouse events count, so our own scripted fills are never learned.
  // Focus events are NOT used: el.focus()/blur() from a script produce trusted focus events too.
  function noteTouch(e) {
    if (!e.isTrusted || S.dead) return;
    // el.click() on a radio/checkbox makes the browser fire *trusted* input/change events, so while we are
    // filling only real key presses and mouse-downs (which scripts cannot produce) count as Rohit's.
    if ((S.running || Date.now() < (S.quietUntil || 0)) && e.type !== "keydown" && e.type !== "pointerdown") return;
    if (e.type === "focusout") {   // leaving a field only schedules learning, it is not a touch
      if (S.touched.length) { clearTimeout(S.learnT); S.learnT = setTimeout(harvest, 1500); }
      return;
    }
    const t = e.composedPath ? e.composedPath()[0] : e.target;
    if (!t || !t.nodeType || (S.host && S.host.contains(t))) return;
    S.touched.push(t); if (S.touched.length > 300) S.touched.splice(0, 100);
    // React often replaces the field's elements after a pick, so also remember *which question* was touched
    try {
      let a = t.nodeType === 1 ? t : t.parentElement;
      for (let k = 0; a && k < 7; k++, a = parentOf(a)) {
        const c = a.matches("input,textarea,select") ? [a]
          : [...a.querySelectorAll("input:not([type=hidden]),textarea,select")].filter((x) => x.getAttribute("aria-hidden") !== "true");
        if (c.length === 1) { const l = low(labelOf(c[0])); if (l) S.touchedLabels.add(l); break; }
        if (c.length > 1) {
          // a radio / checkbox group is still one question
          if (c.every((x) => x.type === c[0].type && x.name && x.name === c[0].name)) {
            const l = low(labelOf(c[0], c)); if (l) S.touchedLabels.add(l);
          }
          break;
        }
      }
    } catch (err) { /* best effort */ }
    clearTimeout(S.learnT);
    // Submit can navigate away at once: learn right now instead of after the pause
    const btn = e.type === "click" && t.closest && t.closest("button,input[type=submit]");
    if (btn && (btn.type === "submit" || /submit|apply|send application/i.test(norm(btn.textContent || btn.value)))) { harvest(); watchApplied(45000); }
    else S.learnT = setTimeout(harvest, 1500);
  }
  ["input", "change", "keydown", "pointerdown", "click", "focusout"].forEach((t) => document.addEventListener(t, noteTouch, true));

  // ---------------------------------------------------------------- submitted?
  // After Rohit clicks Submit, watch for the ATS confirmation and tell the server, which marks the job "applied".
  const APPLIED_RX = /thank(s| you)[^.\n]{0,40}(appl|interest|submitting)|application (has been |was )?(successfully )?(submitted|received|sent)|we('ve| have) received your application|successfully submitted|your application is (complete|on its way)/i;
  function watchApplied(ms, auto = false) {
    if (S.appliedSent || !S.ctx || !S.ctx.job) return;
    if (auto) { try { sessionStorage.setItem("jobfill_auto", S.ctx.job.job_id); } catch (e) { /* ok */ } }
    const t0 = Date.now();
    const tick = () => {
      if (S.appliedSent || !alive()) return;
      const txt = (document.body && document.body.innerText || "").slice(0, 20000);
      if (APPLIED_RX.test(txt)) {
        S.appliedSent = true;
        let auto = false;
        try { auto = sessionStorage.getItem("jobfill_auto") === S.ctx.job.job_id; } catch (e) { /* ok */ }
        // close_tab: only tabs JobFill submitted itself are closed after the confirmation
        send({ type: "applied", payload: { job_id: S.ctx.job.job_id, url: location.href, how: auto ? "jobfill-auto" : "submit-queue" }, close_tab: auto });
        console.info("[JobFill] confirmation seen: job marked applied");
        return;
      }
      if (Date.now() - t0 < ms) setTimeout(tick, 1500);
    };
    setTimeout(tick, 1500);
  }

  function wasTouched(f) {
    const box = f.kind === "combo" ? comboBox(f.el) : null;
    const xs = [f.el, box, ...(f.group || []), ...(f.btns || [])].filter(Boolean);
    return S.touched.some((t) => xs.some((x) => x === t || (x.contains && x.contains(t))));
  }
  function fieldKey(f) {
    const label = f.kind === "buttons" ? questionText(f.btns[0], f.members || f.btns)
      : labelOf(f.el, f.kind === "radio" || f.kind === "checkgroup" ? f.group : null);
    return low(label);
  }
  function currentValue(f) {
    const el = f.el;
    switch (f.kind) {
      case "text": return norm(el.value);
      case "select": {
        const o = el.options[el.selectedIndex];
        return o && el.selectedIndex >= 0 && !/^(select|choose|please|--)/i.test(norm(o.text)) ? norm(o.text) : "";
      }
      case "combo": {
        const box = comboBox(el);
        const sv = box && box.querySelector("[class*=single-value]");
        if (sv) return norm(sv.textContent);
        const mv = box ? [...box.querySelectorAll("[class*=multi-value__label]")].map((x) => norm(x.textContent)) : [];
        return mv.length ? mv.join(" | ") : norm(el.value);
      }
      case "radio": { const r = f.group.find((x) => x.checked); return r ? optLabel(r) : ""; }
      case "checkgroup": return f.group.filter((x) => x.checked).map(optLabel).join(" | ");
      case "buttons": {
        const b = f.btns.find((x) => x.getAttribute("aria-pressed") === "true" || x.getAttribute("aria-checked") === "true" || /selected|active|checked/i.test(x.className));
        return b ? norm(b.textContent) : "";
      }
    }
    return "";
  }
  async function harvest() {
    if (!S.ctx || S.dead) return;
    // a fill pass is running (often triggered by the very change Rohit just made): try again shortly
    if (S.running) { clearTimeout(S.learnT); S.learnT = setTimeout(harvest, 1000); return; }
    const all = S.ctx.rules || [];
    const never = all.filter((r) => r.never), ack = all.filter((r) => r.ack);
    const items = [];
    S.trace = [];
    for (const f of collect()) {
      if (f.kind === "file" || f.kind === "checkbox") continue;
      const label = f.kind === "buttons" ? questionText(f.btns[0], f.members || f.btns)
        : labelOf(f.el, f.kind === "radio" || f.kind === "checkgroup" ? f.group : null);
      if (!wasTouched(f) && !S.touchedLabels.has(low(label))) continue;
      const tr = { label: label.slice(0, 60), kind: f.kind }; S.trace.push(tr);
      if (!label || label.length < 3 || ruleFor(label, never) || ruleFor(label, ack)) continue;
      const val = currentValue(f); tr.val = val;
      if (!val || val.length > 4000) { tr.skip = "no value"; continue; }
      const k = low(label);
      const prev = S.byQuestion.get(label.trim().toLowerCase());
      const pr = prev && prev.r;
      // profile basics (name, email, phone...) come from profile.json, not from learning
      if (f.kind === "text" && /^(first_name|last_name|preferred_name|full_name|email|phone)$/.test(keyFor(f.el, label) || "")) continue;
      tr.prev = pr ? (pr.status + ":" + (pr.value || "")) : null;
      if (pr && (pr.full || pr.value) && norm(pr.full || pr.value) === val) { tr.skip = "same as filled"; continue; }   // unchanged from what we filled
      S.userLabels.add(k); S.status.set(f.el, "user");                // his value wins over any later refill
      if (S.learned.get(k) === val) continue;                          // already sent
      S.learned.set(k, val);
      items.push({ label: norm(label).slice(0, 300), kind: f.kind, value: val, was: pr ? pr.status : null,
                   old: pr && pr.value ? String(pr.value).slice(0, 300) : null, rule: pr ? (pr.key || pr.rule || null) : null });
    }
    if (!items.length) return;
    console.info("[JobFill] learned", items.map((x) => `${x.label} = ${x.value}${x.rule ? " (rule " + x.rule + ")" : ""}`).join("; "));
    S.learnedCount = (S.learnedCount || 0) + items.length;
    if (S.report) renderPanel(S.report);
    try {
      const ok = await send({ type: "learn", payload: { job_id: S.ctx.job && S.ctx.job.job_id, url: location.href, items } });
      if (ok) await getContext();      // pick up the new answers at once (React may re-render fields)
    } catch (e) { /* server down: learned for this page only */ }
  }

  // commands from the popup, or from Claude via window.postMessage({jobfill: "refill"})
  window.addEventListener("message", (e) => {
    if (e.source !== window || !e.data || typeof e.data.jobfill !== "string") return;
    const c = e.data.jobfill;
    if (c === "refill") run({ refresh: true, all: true, force: true });
    else if (c === "clear") clearMarks();
    else if (c === "report") window.postMessage({ jobfillReport: S.report }, "*");
    else if (c === "debug") window.postMessage({ jobfillDebug: { touchedLabels: [...S.touchedLabels], trace: S.trace || null, running: S.running } }, "*");
  });

  let timer = null;
  const obs = new MutationObserver(() => {
    if (S.dead || !S.auto || S.runs > 40) return;
    if (!alive()) { retire(); return; }
    clearTimeout(timer);
    timer = setTimeout(() => {
      const fresh = collect().some((f) => !S.status.has(f.el));
      if (fresh) { S.runs++; run(); }
    }, 900);
  });
  // React sites hydrate after load and throw away anything set before that: wait until the DOM is quiet
  // for a moment (max ~8 s) before the first pass.
  function whenSettled(cb) {
    let t = null; const t0 = Date.now();
    const done = () => { quiet.disconnect(); cb(); };
    const quiet = new MutationObserver(() => {
      clearTimeout(t);
      t = setTimeout(done, Date.now() - t0 > 8000 ? 0 : 1200);
    });
    quiet.observe(document.documentElement, { childList: true, subtree: true, attributes: true });
    t = setTimeout(done, 1500);
  }
  chrome.storage.local.get({ auto: true }, ({ auto }) => {
    S.auto = auto;
    if (!auto) return;
    whenSettled(() => {
      run();
      obs.observe(document.documentElement, { childList: true, subtree: true });
      // Greenhouse / Lever confirm on a new page (".../confirmation", ".../thanks")
      if (/confirm|thank|success|submitted/i.test(location.href)) setTimeout(() => watchApplied(15000), 3000);
    });
  });
})();

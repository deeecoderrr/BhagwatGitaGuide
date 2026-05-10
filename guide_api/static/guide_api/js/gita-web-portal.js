(function () {
  "use strict";

  const doc = document;
  const path = window.location.pathname;
  const LANG_KEY = "gita.lang";

  /* ── Language resolution: URL param > data-lang > localStorage > "en" ── */
  const _urlLang = new URLSearchParams(window.location.search).get("language");
  const _storedLang = (() => { try { return localStorage.getItem(LANG_KEY); } catch { return null; } })();
  const lang =
    (_urlLang === "hi" || _urlLang === "en" ? _urlLang : null) ||
    doc.body?.dataset?.lang ||
    doc.body?.dataset?.language ||
    doc.documentElement.getAttribute("lang") ||
    (_storedLang === "hi" ? "hi" : "en");

  /* Save to localStorage whenever URL explicitly specifies a language */
  if (_urlLang === "hi" || _urlLang === "en") {
    try { localStorage.setItem(LANG_KEY, _urlLang); } catch { /* noop */ }
  }

  /* Auto-redirect: if no lang in URL but stored pref is "hi", reload with it */
  if (!_urlLang && _storedLang === "hi" && typeof window !== "undefined") {
    const _u = new URL(window.location.href);
    _u.searchParams.set("language", "hi");
    window.location.replace(_u.toString());
  }

  function _setLang(newLang) {
    try { localStorage.setItem(LANG_KEY, newLang); } catch { /* noop */ }
    const _u = new URL(window.location.href);
    _u.searchParams.set("language", newLang);
    window.location.assign(_u.toString());
  }

  const navItems = [
    { id: "today", label: lang === "hi" ? "आज" : "Today", icon: "⌂", href: `/today/?language=${encodeURIComponent(lang)}`, match: ["/today/"] },
    { id: "ask", label: lang === "hi" ? "पूछें" : "Ask", icon: "♡", href: `/api/chat-ui/?language=${encodeURIComponent(lang)}`, match: ["/api/chat-ui/"] },
    { id: "read", label: lang === "hi" ? "पढ़ें" : "Read", icon: "☰", href: `/api/chat-ui/?language=${encodeURIComponent(lang)}&open_reader=1`, match: ["/read-", "/read/"] },
    { id: "meditate", label: lang === "hi" ? "अभ्यास" : "Practice", icon: "✦", href: `/meditation/?language=${encodeURIComponent(lang)}`, match: ["/meditation/", "/japa/", "/sadhana/", "/practice/"] },
    { id: "journal", label: lang === "hi" ? "डायरी" : "Journal", icon: "◷", href: `/history/?language=${encodeURIComponent(lang)}`, match: ["/history/", "/saved-reflections/", "/gratitude/", "/mood/", "/quote-art/"] },
    { id: "you", label: lang === "hi" ? "अंतर्दृष्टि" : "Insights", icon: "◉", href: `/insights/?language=${encodeURIComponent(lang)}`, match: ["/insights/", "/account/", "/plans/", "/community/", "/support/"] },
  ];

  const quickActions = [
    { title: lang === "hi" ? "कृष्ण से पूछें" : "Ask Krishna", desc: lang === "hi" ? "गीता ज्ञान से मार्गदर्शन" : "Guidance from Gita wisdom", href: `/api/chat-ui/?language=${encodeURIComponent(lang)}` },
    { title: lang === "hi" ? "ध्यान" : "Meditation", desc: lang === "hi" ? "अभ्यास और जप" : "Tracked practice and japa", href: `/meditation/?language=${encodeURIComponent(lang)}` },
    { title: lang === "hi" ? "गीता पढ़ें" : "Read Gita", desc: lang === "hi" ? "अध्याय, श्लोक, टिप्पणियां" : "Chapters, verses, notes", href: `/api/chat-ui/?language=${encodeURIComponent(lang)}&open_reader=1` },
    { title: lang === "hi" ? "अंतर्दृष्टि" : "Insights", desc: lang === "hi" ? "आपकी यात्रा का संक्षिप्त विवरण" : "Your journey snapshot", href: `/insights/?language=${encodeURIComponent(lang)}` },
    { title: lang === "hi" ? "डायरी" : "Journal", desc: lang === "hi" ? "वार्तालाप सूत्र" : "Conversation threads", href: `/history/?language=${encodeURIComponent(lang)}` },
    { title: lang === "hi" ? "सहेजे गए" : "Saved", desc: lang === "hi" ? "सहेजे गए विचार" : "Saved reflections", href: `/saved-reflections/?language=${encodeURIComponent(lang)}` },
    { title: lang === "hi" ? "समुदाय" : "Community", desc: lang === "hi" ? "भक्ति पढ़ें और साझा करें" : "Read and share devotion", href: `/community/?language=${encodeURIComponent(lang)}` },
  ];

  function isActive(item) {
    return item.match.some((m) => path.startsWith(m));
  }

  function getCookie(name) {
    const escaped = name.replace(/[.$?*|{}()[\]\\/+^]/g, "\\$&");
    const match = doc.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : "";
  }

  function getToken() {
    return (
      getCookie("chat_token") ||
      localStorage.getItem("gita_token") ||
      localStorage.getItem("gita.auth.token") ||
      ""
    );
  }

  function portalFetch(url, opts) {
    const token = getToken();
    const headers = {
      Accept: "application/json",
      ...(opts && opts.headers ? opts.headers : {}),
    };
    if (token) headers.Authorization = `Token ${token}`;
    return fetch(url, {
      credentials: "same-origin",
      ...opts,
      headers,
    });
  }

  function createEl(tag, attrs, html) {
    const el = doc.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (key === "class") el.className = value;
      else if (key === "dataset") Object.assign(el.dataset, value);
      else el.setAttribute(key, value);
    });
    if (html != null) el.innerHTML = html;
    return el;
  }

  function toast(message) {
    let node = doc.querySelector("[data-portal-toast]");
    if (!node) {
      node = createEl("div", { class: "portal-toast", "data-portal-toast": "" });
      doc.body.appendChild(node);
    }
    node.textContent = message;
    node.classList.add("open");
    clearTimeout(node._timer);
    node._timer = setTimeout(() => node.classList.remove("open"), 2600);
  }

  function _localizedToast(en, hi) { toast(lang === "hi" ? hi : en); }

  function injectAtmosphere() {
    if (doc.querySelector("[data-portal-vfx]")) return;
    const vfx = createEl(
      "div",
      { class: "portal-vfx", "data-portal-vfx": "", "aria-hidden": "true" },
      '<div class="portal-light-beam"></div><div class="portal-mantra">ॐ</div><div class="portal-mantra">शान्ति</div><div class="portal-mantra">हरि</div>',
    );
    doc.body.prepend(vfx);
  }

  function navMarkup(items, compact) {
    return items
      .map((item) => {
        const active = isActive(item) ? " active" : "";
        if (compact) {
          return `<a class="${active.trim()}" href="${item.href}" data-portal-nav="${item.id}"><span class="portal-nav-icon">${item.icon}</span><span>${item.label}</span></a>`;
        }
        return `<a class="${active.trim()}" href="${item.href}" data-portal-nav="${item.id}">${item.label}</a>`;
      })
      .join("");
  }

  function injectTopbar() {
    if (doc.querySelector("[data-portal-topbar]")) return;
    const topbar = createEl(
      "nav",
      { class: "portal-topbar", "data-portal-topbar": "", "aria-label": "Bhagavad Gita app navigation" },
      `
        <a class="portal-brand" href="/today/?language=${encodeURIComponent(lang)}">
          <span class="portal-brand-mark" aria-hidden="true"></span>
          <span>
            <span class="portal-brand-kicker">${lang === "hi" ? "पूछें · ध्यान करें · स्वस्थ हों" : "Ask · Meditate · Heal"}</span>
            <span class="portal-brand-title">${lang === "hi" ? "भगवद्गीता मार्गदर्शन" : "Bhagavad Gita Guide"}</span>
          </span>
        </a>
        <div class="portal-topnav">${navMarkup(navItems, false)}</div>
        <div class="portal-lang-toggle" aria-label="Change language">
          <button type="button" class="portal-lang-btn${lang === "en" ? " portal-lang-btn-on" : ""}" data-portal-lang="en">EN</button>
          <button type="button" class="portal-lang-btn${lang === "hi" ? " portal-lang-btn-on" : ""}" data-portal-lang="hi">हि</button>
        </div>
        <button type="button" class="portal-command-trigger" data-portal-command>${lang === "hi" ? "मेनू" : "Menu"}</button>
      `,
    );
    topbar.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-portal-lang]");
      if (btn) _setLang(btn.dataset.portalLang);
    });
    doc.body.prepend(topbar);
  }

  function injectBottomNav() {
    if (doc.querySelector("[data-portal-bottom-nav]")) return;
    const bottom = createEl(
      "nav",
      { class: "portal-bottom-nav", "data-portal-bottom-nav": "", "aria-label": "Mobile style navigation" },
      navMarkup(navItems, true),
    );
    doc.body.appendChild(bottom);
  }

  function injectDrawer() {
    if (doc.querySelector("[data-portal-drawer]")) return;
    const drawer = createEl(
      "aside",
      { class: "portal-drawer", "data-portal-drawer": "", "aria-label": "Quick actions" },
      `
        <h2>${lang === "hi" ? "आपको क्या चाहिए?" : "What do you need?"}</h2>
        <p>${lang === "hi" ? "मार्गदर्शन, अभ्यास, गीता पठन, डायरी, और अंतर्दृष्टि के बीच आसानी से नेविगेट करें — ठीक मोबाइल एप की तरह।" : "Move between guidance, practice, reading, journaling, and insights just like the mobile app."}</p>
        <div class="portal-action-grid">
          ${quickActions
            .map(
              (action) => `
                <a class="portal-action-card" href="${action.href}">
                  <strong>${action.title}</strong>
                  <span>${action.desc}</span>
                </a>
              `,
            )
            .join("")}
        </div>
      `,
    );
    const fab = createEl("button", {
      class: "portal-fab",
      type: "button",
      "data-portal-fab": "",
      "aria-label": "Open quick actions",
    });
    fab.textContent = "✦";
    doc.body.append(drawer, fab);
  }

  function injectSkipLink() {
    if (doc.querySelector(".portal-skip-link")) return;
    const main = doc.querySelector("main") || doc.querySelector(".main") || doc.querySelector(".app-shell");
    if (!main) return;
    if (!main.id) main.id = "main-content";
    const link = createEl("a", { class: "portal-skip-link", href: `#${main.id}` }, "Skip to content");
    doc.body.prepend(link);
  }

  function normalizeLegacyAuthLinks() {
    doc.querySelectorAll('a[href="/auth/"], a[href="/auth"]').forEach((link) => {
      link.setAttribute("href", `/api/chat-ui/?language=${encodeURIComponent(lang)}#guest-auth-target`);
    });
  }

  function enhanceShareButtons() {
    doc.querySelectorAll("[data-portal-share], .share-btn, .share-button").forEach((button) => {
      if (button.dataset.portalEnhanced) return;
      button.dataset.portalEnhanced = "1";
      button.addEventListener("click", async () => {
        try {
          if (navigator.share) {
            await navigator.share({ title: doc.title, url: window.location.href });
          } else {
            await navigator.clipboard.writeText(window.location.href);
            toast(lang === "hi" ? "लिंक कॉपी किया गया" : "Link copied");
          }
        } catch {
          /* user cancelled */
        }
      });
    });
  }

  function wireGlobalEvents() {
    doc.addEventListener("click", (event) => {
      const trigger = event.target.closest("[data-portal-fab], [data-portal-command]");
      if (trigger) {
        doc.querySelector("[data-portal-drawer]")?.classList.toggle("open");
        return;
      }
      const drawer = doc.querySelector("[data-portal-drawer]");
      if (drawer && drawer.classList.contains("open")) {
        const clickedInside = event.target.closest("[data-portal-drawer], [data-portal-fab], [data-portal-command]");
        if (!clickedInside) drawer.classList.remove("open");
      }
    });

    doc.addEventListener("keydown", (event) => {
      if (event.key === "Escape") doc.querySelector("[data-portal-drawer]")?.classList.remove("open");
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        doc.querySelector("[data-portal-drawer]")?.classList.toggle("open");
      }
    });
  }

  async function hydrateAuthState() {
    const token = getToken();
    doc.body.dataset.portalAuth = token ? "token" : "unknown";
    if (!token) return;
    try {
      const res = await portalFetch("/api/v1/auth/me/");
      if (!res.ok) throw new Error("auth");
      const data = await res.json();
      doc.body.dataset.portalAuth = "signed-in";
      if (data.username) doc.body.dataset.portalUsername = data.username;
      const brandKicker = doc.querySelector(".portal-brand-kicker");
      if (brandKicker && data.username) brandKicker.textContent = lang === "hi" ? `नमस्कार · ${data.username}` : `Welcome back · ${data.username}`;
    } catch {
      doc.body.dataset.portalAuth = "signed-out";
    }
  }

  function markReady() {
    doc.documentElement.classList.add("gita-web-portal-ready");
    doc.body.classList.add("gita-web-app");
  }

  function init() {
    if (!doc.body) return;
    markReady();
    injectSkipLink();
    injectAtmosphere();
    injectTopbar();
    injectBottomNav();
    injectDrawer();
    normalizeLegacyAuthLinks();
    enhanceShareButtons();
    wireGlobalEvents();
    hydrateAuthState();
  }

  if (doc.readyState === "loading") {
    doc.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();

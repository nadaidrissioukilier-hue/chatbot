/**
 * ENTRADE.MA — Widget de chat embarquable (Phase 7 du guide).
 *
 * Usage sur n'importe quelle page :
 *   <script src=".../widget.js" data-api-key="VOTRE_CLE" async></script>
 *
 * Attributs optionnels sur la balise <script> :
 *   data-api-base  — URL de l'API (défaut : http://localhost:8000, pour ce MVP local)
 *   data-lang      — "ar" | "fr" pour forcer la langue d'ouverture (défaut : dernier choix
 *                    utilisateur enregistré, sinon détection navigateur)
 *   data-theme     — "light" | "dark" pour forcer le thème d'ouverture (défaut : dernier choix
 *                    utilisateur enregistré, sinon préférence système)
 *
 * Isolation : tout le widget vit dans un <div> hôte avec Shadow DOM fermé
 * (attachShadow({mode: "closed"})) — le CSS du site hôte ne peut ni casser
 * le widget, ni être cassé par lui. z-index maximal pour rester au-dessus
 * du contenu de la page.
 *
 * Langue et thème sont choisis par l'utilisateur via deux boutons dans
 * l'en-tête (pas seulement déduits automatiquement) et mémorisés en
 * localStorage pour persister d'une visite à l'autre.
 */
(function () {
  "use strict";

  var CURRENT_SCRIPT = document.currentScript;
  var API_KEY = CURRENT_SCRIPT.getAttribute("data-api-key") || "";
  var API_BASE = CURRENT_SCRIPT.getAttribute("data-api-base") || "http://localhost:8000";
  var FORCED_LANG = CURRENT_SCRIPT.getAttribute("data-lang") || null;
  var FORCED_THEME = CURRENT_SCRIPT.getAttribute("data-theme") || null;

  if (!API_KEY) {
    console.error("[entraide-widget] data-api-key manquant sur la balise <script> — widget non initialisé.");
    return;
  }

  var LS_LANG_KEY = "entraide_widget_lang";
  var LS_THEME_KEY = "entraide_widget_theme";
  var LS_SESSION_KEY = "entraide_widget_session";

  function storageGet(key) {
    try { return window.localStorage.getItem(key); } catch (e) { return null; }
  }
  function storageSet(key, value) {
    try { window.localStorage.setItem(key, value); } catch (e) { /* stockage indisponible (iframe sandboxée, etc.) — ignoré */ }
  }

  // Mémoire conversationnelle (2026-08-15) : un session_id stable pour toute
  // la visite (persisté en localStorage, pas juste en mémoire JS, pour
  // survivre à un refresh de page) permet au backend de relier les tours
  // d'une même conversation (voir src/tools/session_memory.py) -- sans ça,
  // chaque question repart de zéro et une question de suivi elliptique
  // ("و ما هي الشروط والوثائق المطلوبة") perd tout contexte.
  function makeSessionId() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "en-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
  }
  var SESSION_ID = storageGet(LS_SESSION_KEY);
  if (!SESSION_ID) {
    SESSION_ID = makeSessionId();
    storageSet(LS_SESSION_KEY, SESSION_ID);
  }

  var STYLE = "\
    :host, .en-root { all: initial; }\
    * { box-sizing: border-box; font-family: -apple-system, 'Segoe UI', 'Noto Sans', 'Noto Sans Arabic', sans-serif; }\
    .en-root {\
      --en-accent: #12684F; --en-accent-ink: #0B4536; --en-accent-soft: #DCEAE3;\
      --en-ink: #1B1F1D; --en-paper: #FFFFFF; --en-raised: #F7F6F0; --en-line: rgba(27,31,29,0.14); --en-muted: #5B6660;\
      position: fixed; bottom: 20px; right: 20px; z-index: 2147483647;\
      display: flex; flex-direction: column; align-items: flex-end;\
    }\
    @media (prefers-color-scheme: dark) {\
      .en-root:not([data-theme='light']) {\
        --en-accent: #49AE8B; --en-accent-ink: #8CD3B7; --en-accent-soft: #1C332A;\
        --en-ink: #ECEAE2; --en-paper: #1A1F19; --en-raised: #202620; --en-line: rgba(236,234,226,0.16); --en-muted: #9BA69E;\
      }\
    }\
    .en-root[data-theme='dark'] {\
      --en-accent: #49AE8B; --en-accent-ink: #8CD3B7; --en-accent-soft: #1C332A;\
      --en-ink: #ECEAE2; --en-paper: #1A1F19; --en-raised: #202620; --en-line: rgba(236,234,226,0.16); --en-muted: #9BA69E;\
    }\
    .en-root[data-theme='light'] {\
      --en-accent: #12684F; --en-accent-ink: #0B4536; --en-accent-soft: #DCEAE3;\
      --en-ink: #1B1F1D; --en-paper: #FFFFFF; --en-raised: #F7F6F0; --en-line: rgba(27,31,29,0.14); --en-muted: #5B6660;\
    }\
    .en-launcher {\
      width: 56px; height: 56px; border-radius: 50%; background: var(--en-accent);\
      border: none; cursor: pointer; box-shadow: 0 4px 16px rgba(0,0,0,0.25);\
      display: flex; align-items: center; justify-content: center; color: #fff;\
      transition: transform 0.15s ease;\
    }\
    .en-launcher:hover { transform: scale(1.06); }\
    .en-launcher svg { width: 26px; height: 26px; }\
    .en-panel {\
      width: 380px; max-width: calc(100vw - 40px); height: 550px; max-height: calc(100vh - 100px);\
      background: var(--en-paper); border-radius: 14px; box-shadow: 0 8px 32px rgba(0,0,0,0.28);\
      display: none; flex-direction: column; overflow: hidden; margin-bottom: 12px;\
      border: 1px solid var(--en-line);\
    }\
    .en-panel.en-open { display: flex; }\
    .en-header {\
      background: var(--en-accent); color: #fff; padding: 12px 14px;\
      display: flex; align-items: center; gap: 8px; flex: none;\
    }\
    .en-header .en-title-wrap { display: flex; flex-direction: column; gap: 1px; min-width: 0; }\
    .en-header .en-title { font-size: 14px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }\
    .en-header .en-subtitle { font-size: 10.5px; opacity: 0.82; display: flex; align-items: center; gap: 5px; }\
    .en-header .en-status-dot { width: 7px; height: 7px; border-radius: 50%; background: #9BE8CE; flex: none; }\
    .en-header .en-actions { margin-inline-start: auto; display: flex; align-items: center; gap: 2px; flex: none; }\
    .en-iconbtn {\
      background: rgba(255,255,255,0.14); border: none; color: #fff; cursor: pointer;\
      border-radius: 7px; padding: 5px 7px; font-size: 11px; font-weight: 700;\
      display: flex; align-items: center; justify-content: center; line-height: 1;\
      transition: background 0.12s ease; letter-spacing: 0.02em;\
    }\
    .en-iconbtn:hover { background: rgba(255,255,255,0.26); }\
    .en-iconbtn svg { width: 15px; height: 15px; }\
    .en-messages { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; background: var(--en-paper); }\
    .en-msg { max-width: 85%; padding: 9px 12px; border-radius: 11px; font-size: 13.5px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; color: var(--en-ink); }\
    .en-msg.en-user { align-self: flex-end; background: var(--en-accent); color: #fff; border-bottom-right-radius: 3px; }\
    .en-msg.en-bot { align-self: flex-start; background: var(--en-raised); border: 1px solid var(--en-line); border-bottom-left-radius: 3px; }\
    .en-msg.en-welcome { align-self: stretch; max-width: 100%; background: var(--en-accent-soft); border: 1px solid var(--en-line); color: var(--en-ink); }\
    .en-msg.en-rtl { direction: rtl; text-align: right; }\
    .en-msg.en-rtl.en-user { border-bottom-right-radius: 11px; border-bottom-left-radius: 3px; }\
    .en-msg .en-sources { margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--en-line); font-size: 11px; color: var(--en-muted); }\
    .en-thinking { align-self: flex-start; font-size: 12px; color: var(--en-muted); padding: 8px 12px; display: flex; align-items: center; gap: 7px; }\
    .en-spin { width: 11px; height: 11px; border: 2px solid var(--en-line); border-top-color: var(--en-accent); border-radius: 50%; animation: en-spin 0.8s linear infinite; }\
    @keyframes en-spin { to { transform: rotate(360deg); } }\
    .en-inputrow { display: flex; gap: 8px; padding: 10px; border-top: 1px solid var(--en-line); flex: none; background: var(--en-paper); }\
    .en-inputrow input { flex: 1; padding: 9px 11px; border-radius: 8px; border: 1px solid var(--en-line); background: var(--en-raised); color: var(--en-ink); font-size: 13.5px; min-width: 0; }\
    .en-inputrow input:focus { outline: 2px solid var(--en-accent-soft); }\
    .en-inputrow button { padding: 0 14px; border: none; border-radius: 8px; background: var(--en-accent); color: #fff; font-weight: 600; font-size: 13px; cursor: pointer; flex: none; }\
    .en-inputrow button:disabled { opacity: 0.5; cursor: default; }\
    .en-hint { font-size: 10.5px; color: var(--en-muted); padding: 0 10px 8px; }\
  ";

  var ICON_CHAT = '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3C7.03 3 3 6.58 3 11c0 2.39 1.19 4.53 3.08 6.02L5 21l4.24-1.7c.87.2 1.79.3 2.76.3 4.97 0 9-3.58 9-8s-4.03-8-9-8Z" fill="currentColor"/></svg>';
  var ICON_CLOSE = '<svg viewBox="0 0 24 24" fill="none"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  var ICON_SUN = '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="4.2" fill="currentColor"/><path d="M12 2.5v2.4M12 19.1v2.4M4.4 4.4l1.7 1.7M17.9 17.9l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.4 19.6l1.7-1.7M17.9 6.1l1.7-1.7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
  var ICON_MOON = '<svg viewBox="0 0 24 24" fill="none"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z" fill="currentColor"/></svg>';

  function isArabic(text) { return /[؀-ۿ]/.test(text); }

  function detectBrowserLang() {
    var nav = (navigator.language || "fr").toLowerCase();
    return nav.indexOf("ar") === 0 ? "ar" : "fr";
  }
  function detectSystemTheme() {
    return (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
  }

  // --- Internationalisation de l'interface (indépendante de la langue des
  // messages, qui suit le contenu réel via isArabic()) ---
  var I18N = {
    fr: {
      title: "Assistant — Entraide Nationale",
      subtitle: "En ligne",
      placeholder: "Écrivez votre question…",
      send: "Envoyer",
      hint: "La réponse peut prendre un moment",
      thinking: "Recherche en cours…",
      error: "Service temporairement indisponible.",
      welcome: "Bonjour, je suis l'assistant virtuel de l'Entraide Nationale. Je suis là pour vous orienter vers les centres, services et programmes qui peuvent vous aider — posez-moi votre question quand vous voulez.",
      langToggleLabel: "AR",
      langToggleTitle: "Passer à l'arabe",
      themeToggleTitleToDark: "Activer le thème sombre",
      themeToggleTitleToLight: "Activer le thème clair",
      openLabel: "Ouvrir le chat",
      closeLabel: "Fermer",
    },
    ar: {
      title: "المساعد — التعاون الوطني",
      subtitle: "متصل الآن",
      placeholder: "اكتب سؤالك هنا…",
      send: "إرسال",
      hint: "قد يستغرق الرد بعض الوقت",
      thinking: "جارٍ البحث...",
      error: "الخدمة غير متوفرة مؤقتاً.",
      welcome: "مرحباً بك، أنا المساعد الافتراضي للتعاون الوطني. أنا هنا لمساعدتك في العثور على المراكز والخدمات والبرامج التي قد تفيدك — اطرح سؤالك متى شئت.",
      langToggleLabel: "FR",
      langToggleTitle: "التبديل إلى الفرنسية",
      themeToggleTitleToDark: "تفعيل الوضع الداكن",
      themeToggleTitleToLight: "تفعيل الوضع الفاتح",
      openLabel: "فتح المحادثة",
      closeLabel: "إغلاق",
    },
  };

  function init() {
    var lang = FORCED_LANG || storageGet(LS_LANG_KEY) || detectBrowserLang();
    if (lang !== "ar" && lang !== "fr") lang = "fr";
    var theme = FORCED_THEME || storageGet(LS_THEME_KEY) || detectSystemTheme();
    if (theme !== "light" && theme !== "dark") theme = "light";

    var host = document.createElement("div");
    host.id = "entraide-widget-host";
    document.body.appendChild(host);
    var shadow = host.attachShadow({ mode: "closed" });

    var styleEl = document.createElement("style");
    styleEl.textContent = STYLE;
    shadow.appendChild(styleEl);

    var root = document.createElement("div");
    root.className = "en-root";
    root.setAttribute("data-theme", theme);
    root.innerHTML =
      '<div class="en-panel" id="en-panel">' +
        '<div class="en-header">' +
          '<span class="en-status-dot" id="en-status-dot"></span>' +
          '<div class="en-title-wrap">' +
            '<span class="en-title" id="en-title"></span>' +
            '<span class="en-subtitle" id="en-subtitle"></span>' +
          '</div>' +
          '<div class="en-actions">' +
            '<button class="en-iconbtn" id="en-lang-toggle" type="button"></button>' +
            '<button class="en-iconbtn" id="en-theme-toggle" type="button"></button>' +
            '<button class="en-iconbtn" id="en-close" type="button">' + ICON_CLOSE + '</button>' +
          '</div>' +
        '</div>' +
        '<div class="en-messages" id="en-messages"></div>' +
        '<form class="en-inputrow" id="en-form">' +
          '<input id="en-input" type="text" autocomplete="off">' +
          '<button type="submit" id="en-send"></button>' +
        '</form>' +
        '<div class="en-hint" id="en-hint"></div>' +
      '</div>' +
      '<button class="en-launcher" id="en-launcher"></button>';
    shadow.appendChild(root);

    var panel = shadow.getElementById("en-panel");
    var launcher = shadow.getElementById("en-launcher");
    var closeBtn = shadow.getElementById("en-close");
    var titleEl = shadow.getElementById("en-title");
    var subtitleEl = shadow.getElementById("en-subtitle");
    var messagesEl = shadow.getElementById("en-messages");
    var form = shadow.getElementById("en-form");
    var input = shadow.getElementById("en-input");
    var sendBtn = shadow.getElementById("en-send");
    var hintEl = shadow.getElementById("en-hint");
    var statusDot = shadow.getElementById("en-status-dot");
    var langToggle = shadow.getElementById("en-lang-toggle");
    var themeToggle = shadow.getElementById("en-theme-toggle");

    var welcomeEl = null; // référence pour pouvoir la retraduire si la langue change avant tout message utilisateur
    var userHasSentMessage = false;

    function t() { return I18N[lang]; }

    function applyDirection() {
      var dir = lang === "ar" ? "rtl" : "ltr";
      panel.setAttribute("dir", dir);
    }

    function renderChrome() {
      var strings = t();
      titleEl.textContent = strings.title;
      subtitleEl.textContent = strings.subtitle;
      input.placeholder = strings.placeholder;
      sendBtn.textContent = strings.send;
      hintEl.textContent = strings.hint;
      launcher.setAttribute("aria-label", strings.openLabel);
      closeBtn.setAttribute("aria-label", strings.closeLabel);
      launcher.innerHTML = panel.classList.contains("en-open") ? ICON_CLOSE : ICON_CHAT;

      langToggle.textContent = strings.langToggleLabel;
      langToggle.title = strings.langToggleTitle;
      langToggle.setAttribute("aria-label", strings.langToggleTitle);

      var themeIsDark = root.getAttribute("data-theme") === "dark";
      themeToggle.innerHTML = themeIsDark ? ICON_SUN : ICON_MOON;
      themeToggle.title = themeIsDark ? strings.themeToggleTitleToLight : strings.themeToggleTitleToDark;
      themeToggle.setAttribute("aria-label", themeToggle.title);

      applyDirection();

      if (welcomeEl && !userHasSentMessage) {
        welcomeEl.textContent = strings.welcome;
        welcomeEl.className = "en-msg en-bot en-welcome" + (lang === "ar" ? " en-rtl" : "");
      }
    }

    function addMessage(text, role) {
      var div = document.createElement("div");
      div.className = "en-msg en-" + role + (isArabic(text) ? " en-rtl" : "");
      div.textContent = text;
      messagesEl.appendChild(div);
      messagesEl.scrollTop = messagesEl.scrollHeight;
      return div;
    }

    function showWelcome() {
      welcomeEl = document.createElement("div");
      welcomeEl.textContent = t().welcome;
      welcomeEl.className = "en-msg en-bot en-welcome" + (lang === "ar" ? " en-rtl" : "");
      messagesEl.appendChild(welcomeEl);
    }

    renderChrome();
    showWelcome();

    langToggle.addEventListener("click", function () {
      lang = lang === "ar" ? "fr" : "ar";
      storageSet(LS_LANG_KEY, lang);
      renderChrome();
    });

    themeToggle.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      storageSet(LS_THEME_KEY, next);
      renderChrome();
    });

    launcher.addEventListener("click", function () {
      panel.classList.toggle("en-open");
      launcher.innerHTML = panel.classList.contains("en-open") ? ICON_CLOSE : ICON_CHAT;
      if (panel.classList.contains("en-open")) input.focus();
    });
    closeBtn.addEventListener("click", function () {
      panel.classList.remove("en-open");
      launcher.innerHTML = ICON_CHAT;
    });

    function checkHealth() {
      fetch(API_BASE + "/health")
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var ok = Object.keys(d.services).every(function (k) { return d.services[k] === "ok"; });
          statusDot.style.background = ok ? "#9BE8CE" : "#E0A05C";
        })
        .catch(function () { statusDot.style.background = "#E08B62"; });
    }
    checkHealth();
    setInterval(checkHealth, 20000);

    function addThinking() {
      var div = document.createElement("div");
      div.className = "en-thinking";
      div.innerHTML = '<span class="en-spin"></span><span>' + t().thinking + '</span>';
      messagesEl.appendChild(div);
      messagesEl.scrollTop = messagesEl.scrollHeight;
      return div;
    }

    function sendQuery(query) {
      var thinkingEl = addThinking();
      var botEl = null;
      var fullText = "";

      return fetch(API_BASE + "/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": API_KEY },
        body: JSON.stringify({ query: query, session_id: SESSION_ID }),
      })
        .then(function (resp) {
          if (!resp.ok) throw new Error("HTTP " + resp.status);
          var reader = resp.body.getReader();
          var decoder = new TextDecoder();
          var buffer = "";

          function pump() {
            return reader.read().then(function (res) {
              if (res.done) return;
              buffer += decoder.decode(res.value, { stream: true });
              var parts = buffer.split("\n\n");
              buffer = parts.pop();

              parts.forEach(function (part) {
                if (part.indexOf("data: ") !== 0) return;
                var payload = part.slice(6).trim();
                if (payload === "[DONE]") return;
                var data;
                try { data = JSON.parse(payload); } catch (e) { return; }

                if (data.chunk) {
                  if (!botEl) { thinkingEl.remove(); botEl = addMessage("", "bot"); }
                  fullText += data.chunk;
                  botEl.textContent = fullText;
                  if (isArabic(fullText)) botEl.classList.add("en-rtl");
                  messagesEl.scrollTop = messagesEl.scrollHeight;
                } else if (data.event === "done" && data.sources && data.sources.length && botEl) {
                  var srcDiv = document.createElement("div");
                  srcDiv.className = "en-sources";
                  srcDiv.innerHTML = data.sources.slice(0, 3).map(function (s) {
                    return "• " + (s.name || "") + (s.region ? " — " + s.region : "");
                  }).join("<br>");
                  botEl.appendChild(srcDiv);
                  messagesEl.scrollTop = messagesEl.scrollHeight;
                }
              });
              return pump();
            });
          }
          return pump();
        })
        .then(function () {
          if (!botEl) { thinkingEl.remove(); addMessage(t().error, "bot"); }
        })
        .catch(function (err) {
          thinkingEl.remove();
          addMessage(t().error, "bot");
        });
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var query = input.value.trim();
      if (!query) return;
      userHasSentMessage = true;
      addMessage(query, "user");
      input.value = "";
      sendBtn.disabled = true;
      sendQuery(query).finally(function () { sendBtn.disabled = false; input.focus(); });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

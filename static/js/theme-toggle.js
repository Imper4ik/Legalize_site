/* static/js/theme-toggle.js */
(function () {
  // защита от двойной инициализации
  if (typeof window !== "undefined") {
    if (window.__themeToggleInitialized) return;
    window.__themeToggleInitialized = true;
  }

  var STORAGE_KEY = "preferredTheme";
  var toggles = [];
  var docEl = document.documentElement;
  var body = document.body;
  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function safeGet() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (_) { return null; }
  }
  function safeSet(v) {
    try { localStorage.setItem(STORAGE_KEY, v); } catch (_) {}
  }

  function normalize(theme) {
    return theme === "dark" ? "dark" : "light";
  }

  function setAttrs(theme) {
    // поддерживаем обе схемы: твои CSS и Bootstrap 5.3
    docEl.setAttribute("data-theme", theme);
    docEl.setAttribute("data-bs-theme", theme);
    if (body) {
      body.setAttribute("data-theme", theme);
      body.setAttribute("data-bs-theme", theme);
    }
    // опциональные классы, если где-то используешь
    docEl.classList.toggle("theme-dark", theme === "dark");
    docEl.classList.toggle("theme-light", theme !== "dark");

    // meta color-scheme для корректных нативных контролов
    var meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) meta.setAttribute("content", theme === "dark" ? "dark light" : "light dark");
  }

  function updateToggle(btn, theme) {
    // aria
    btn.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");

    // текст в дочернем элементе с data-theme-toggle-text
    var txt = btn.querySelector("[data-theme-toggle-text]");
    if (txt) {
      var nextText = theme === "dark" ? btn.dataset.themeDarkText : btn.dataset.themeLightText;
      if (nextText) txt.textContent = nextText;
    }

    // подсказки (по желанию, если заданы)
    var title = theme === "dark" ? btn.dataset.themeDarkTitle : btn.dataset.themeLightTitle;
    if (title) btn.setAttribute("title", title);
    var label = theme === "dark" ? btn.dataset.themeDarkLabel : btn.dataset.themeLightLabel;
    if (label) btn.setAttribute("aria-label", label);
  }

  function apply(theme) {
    var t = normalize(theme);
    setAttrs(t);
    for (var i = 0; i < toggles.length; i++) updateToggle(toggles[i], t);
  }

  function getCurrent() {
    return (
      docEl.getAttribute("data-theme") ||
      docEl.getAttribute("data-bs-theme") ||
      "light"
    );
  }

  function nextTheme() {
    return getCurrent() === "dark" ? "light" : "dark";
  }

  function handleSystemChange(e) {
    // если пользователь явно не выбирал — следуем системе
    if (!safeGet()) apply(e.matches ? "dark" : "light");
  }

  function setupToggle(btn) {
    toggles.push(btn);
    btn.addEventListener("click", function () {
      var t = nextTheme();
      apply(t);
      safeSet(t);
    });
  }

  function injectMobileNotificationStyles() {
    if (document.getElementById("mobile-notification-nav-styles")) return;

    var style = document.createElement("style");
    style.id = "mobile-notification-nav-styles";
    style.textContent = [
      "@media (max-width: 991.98px) {",
      "  .navbar-mobile-actions { display: flex; align-items: center; }",
      "  .navbar-mobile-notification-button { position: relative; display: inline-grid; width: 42px; height: 42px; place-items: center; color: var(--nav-fg); background: color-mix(in srgb, var(--surface) 82%, transparent); border: 1px solid var(--border); border-radius: 12px; transition: color .2s ease, background-color .2s ease, border-color .2s ease, transform .2s ease; }",
      "  .navbar-mobile-notification-button:hover, .navbar-mobile-notification-button:focus-visible { color: var(--brand-1); background: color-mix(in srgb, var(--brand-1) 10%, var(--surface)); border-color: color-mix(in srgb, var(--brand-1) 44%, var(--border)); outline: none; }",
      "  .navbar-mobile-notification-button:active { transform: scale(.96); }",
      "  .navbar-mobile-notification-button i { font-size: 1.18rem; }",
      "  .navbar-mobile-notification-badge { position: absolute; top: -.35rem; right: -.45rem; min-width: 1.25rem; height: 1.25rem; padding: 0 .3rem; display: inline-flex; align-items: center; justify-content: center; color: #fff; background: #dc3545; border: 2px solid var(--nav-bg); border-radius: 999px; font-size: .65rem; font-weight: 700; line-height: 1; }",
      "  .mobile-notifications-menu { min-width: min(21rem, calc(100vw - 2rem)); max-height: min(70vh, 30rem); overflow-y: auto; }",
      "  .theme-navbar .container { flex-wrap: nowrap; }",
      "  .theme-navbar .navbar-brand { min-width: 0; }",
      "  .theme-navbar .navbar-toggler { flex: 0 0 auto; }",
      "  .mobile-nav-bar { justify-content: space-evenly; }",
      "  body { padding-bottom: calc(78px + env(safe-area-inset-bottom)) !important; }",
      "}"
    ].join("\n");
    document.head.appendChild(style);
  }

  function cloneMenuItems(sourceMenu, targetMenu) {
    if (!sourceMenu || !targetMenu) return false;

    var items = sourceMenu.children;
    var copied = false;
    for (var i = 0; i < items.length; i++) {
      targetMenu.appendChild(items[i].cloneNode(true));
      copied = true;
    }
    return copied;
  }

  function setupMobileNotificationMenu() {
    var navbarContainer = document.querySelector(".theme-navbar .container");
    var navbarToggler = document.querySelector(".theme-navbar .navbar-toggler");
    var mobileNav = document.querySelector(".mobile-nav-bar");
    if (!navbarContainer || !navbarToggler || !mobileNav) return;
    if (document.getElementById("mobileNotificationDropdown")) return;

    var reminderIcon = document.querySelector("#navbarNav .nav-item.dropdown .bi.bi-bell");
    var reminderNavItem = reminderIcon ? reminderIcon.closest(".nav-item.dropdown") : null;
    var reminderMenu = reminderNavItem ? reminderNavItem.querySelector(".dropdown-menu") : null;
    if (!reminderMenu) return;

    var mobileReminderLink = mobileNav.querySelector('a[href*="document_reminder_list"]');
    if (mobileReminderLink) mobileReminderLink.remove();

    var attentionBadge = mobileNav.querySelector('a[href*="client_list"] .badge');
    var attentionCount = attentionBadge ? attentionBadge.textContent.trim() : "";

    var wrapper = document.createElement("div");
    wrapper.className = "navbar-mobile-actions d-lg-none ms-auto me-2";

    var dropdown = document.createElement("div");
    dropdown.className = "dropdown";

    var button = document.createElement("button");
    button.id = "mobileNotificationDropdown";
    button.type = "button";
    button.className = "navbar-mobile-notification-button";
    button.setAttribute("data-bs-toggle", "dropdown");
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", "Напоминания");
    button.setAttribute("title", "Напоминания");
    button.innerHTML = '<i class="bi bi-bell-fill" aria-hidden="true"></i>';

    if (attentionCount) {
      var badge = document.createElement("span");
      badge.className = "navbar-mobile-notification-badge";
      badge.textContent = attentionCount;
      button.appendChild(badge);
    }

    var menu = document.createElement("ul");
    menu.className = "dropdown-menu dropdown-menu-end shadow-sm mobile-notifications-menu";
    menu.setAttribute("aria-labelledby", "mobileNotificationDropdown");

    var attentionDropdown = document.querySelector("#navbarNav .badge.bg-danger")?.closest(".dropdown");
    var attentionMenu = attentionDropdown ? attentionDropdown.querySelector(".dropdown-menu") : null;
    var hasAttentionItems = cloneMenuItems(attentionMenu, menu);
    if (hasAttentionItems) {
      var divider = document.createElement("li");
      divider.innerHTML = '<hr class="dropdown-divider">';
      menu.appendChild(divider);
    }

    cloneMenuItems(reminderMenu, menu);
    dropdown.appendChild(button);
    dropdown.appendChild(menu);
    wrapper.appendChild(dropdown);
    navbarContainer.insertBefore(wrapper, navbarToggler);
    injectMobileNotificationStyles();
  }

  function init() {
    // соберём все кнопки
    var nodes = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < nodes.length; i++) setupToggle(nodes[i]);

    // первичная установка: сохранённое → системное → light
    var stored = safeGet();
    if (stored) apply(stored);
    else if (mq && typeof mq.matches === "boolean") apply(mq.matches ? "dark" : "light");
    else apply("light");

    setupMobileNotificationMenu();

    // слушаем смену системной темы, если пользователь не переопределил
    if (mq) {
      if (typeof mq.addEventListener === "function") mq.addEventListener("change", handleSystemChange);
      else if (typeof mq.addListener === "function") mq.addListener(handleSystemChange);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

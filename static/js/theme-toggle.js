/* static/js/theme-toggle.js */
(function () {
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

  function safeSet(value) {
    try { localStorage.setItem(STORAGE_KEY, value); } catch (_) {}
  }

  function normalize(theme) {
    return theme === "dark" ? "dark" : "light";
  }

  function applyTheme(theme) {
    theme = normalize(theme);
    docEl.setAttribute("data-theme", theme);
    docEl.setAttribute("data-bs-theme", theme);

    if (body) {
      body.setAttribute("data-theme", theme);
      body.setAttribute("data-bs-theme", theme);
    }

    docEl.classList.toggle("theme-dark", theme === "dark");
    docEl.classList.toggle("theme-light", theme !== "dark");

    var meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) meta.setAttribute("content", theme === "dark" ? "dark light" : "light dark");

    for (var i = 0; i < toggles.length; i++) {
      var button = toggles[i];
      button.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      var label = button.querySelector("[data-theme-toggle-text]");
      if (label) {
        label.textContent = theme === "dark" ? button.dataset.themeDarkText : button.dataset.themeLightText;
      }
    }
  }

  function currentTheme() {
    return docEl.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function injectMobileStyles() {
    if (document.getElementById("mobile-navigation-styles")) return;

    var style = document.createElement("style");
    style.id = "mobile-navigation-styles";
    style.textContent = [
      "@media (max-width: 991.98px) {",
      "  .theme-navbar { position: relative; z-index: 1060; }",
      "  .theme-navbar .container { flex-wrap: nowrap; }",
      "  .theme-navbar .navbar-toggler, .theme-navbar #navbarNav { display: none !important; }",
      "  .theme-navbar .navbar-brand { min-width: 0; }",
      "  .mobile-header-actions { display: flex; align-items: center; margin-left: auto; margin-right: .35rem; }",
      "  .mobile-header-actions > .dropdown { position: static; }",
      "  .mobile-header-notification-button { position: relative; display: inline-grid; place-items: center; width: 42px; height: 42px; color: var(--nav-fg); background: color-mix(in srgb, var(--surface) 82%, transparent); border: 1px solid var(--border); border-radius: 12px; }",
      "  .mobile-header-notification-button:hover, .mobile-header-notification-button:focus-visible { color: var(--brand-1); background: color-mix(in srgb, var(--brand-1) 10%, var(--surface)); border-color: color-mix(in srgb, var(--brand-1) 44%, var(--border)); outline: none; }",
      "  .mobile-header-notification-button i { font-size: 1.18rem; }",
      "  .mobile-header-notification-badge { position: absolute; top: -.35rem; right: -.45rem; min-width: 1.25rem; height: 1.25rem; padding: 0 .3rem; display: inline-flex; align-items: center; justify-content: center; color: #fff; background: #dc3545; border: 2px solid var(--nav-bg); border-radius: 999px; font-size: .65rem; font-weight: 700; line-height: 1; }",
      "  .mobile-notifications-menu.show { position: fixed !important; top: calc(env(safe-area-inset-top) + 5rem) !important; left: .75rem !important; right: .75rem !important; width: auto !important; max-width: none !important; max-height: calc(100dvh - 6rem); margin: 0 !important; padding: .35rem 0; overflow-y: auto; transform: none !important; z-index: 1080; }",
      "  .mobile-notifications-menu .dropdown-header { padding: .6rem .9rem .35rem; white-space: normal; }",
      "  .mobile-notifications-menu .dropdown-item { display: flex; align-items: flex-start !important; gap: .7rem; padding: .7rem .9rem; white-space: normal; overflow-wrap: anywhere; line-height: 1.25; }",
      "  .mobile-notifications-menu .dropdown-item > span:first-child { min-width: 0; flex: 1 1 auto; }",
      "  .mobile-notifications-menu .dropdown-item .badge { flex: 0 0 auto; margin-top: .05rem; }",
      "  .mobile-nav-bar { grid-template-columns: repeat(4, minmax(0, 1fr)) !important; }",
      "  .mobile-nav-bar > .mobile-nav-item, .mobile-nav-bar > .dropup { min-width: 0; }",
      "  .mobile-nav-menu .dropdown-menu.show { position: fixed !important; left: .5rem !important; right: .5rem !important; bottom: calc(74px + env(safe-area-inset-bottom)) !important; width: auto !important; max-width: none !important; max-height: min(62dvh, 32rem); margin: 0 !important; overflow-y: auto; transform: none !important; z-index: 1080; }",
      "  .mobile-nav-menu .dropdown-item { white-space: normal; }",
      "  body { padding-bottom: calc(86px + env(safe-area-inset-bottom)) !important; }",
      "}"
    ].join("\n");

    document.head.appendChild(style);
  }

  function copyMenuItems(sourceMenu, targetMenu) {
    if (!sourceMenu || !targetMenu) return false;

    var children = sourceMenu.children;
    var copied = false;
    for (var i = 0; i < children.length; i++) {
      targetMenu.appendChild(children[i].cloneNode(true));
      copied = true;
    }
    return copied;
  }

  function setupMobileNotifications() {
    var navbarContainer = document.querySelector(".theme-navbar .container");
    var navbarToggler = document.querySelector(".theme-navbar .navbar-toggler");
    var mobileNav = document.querySelector(".mobile-nav-bar");
    var desktopReminderIcon = document.querySelector("#navbarNav .nav-item.dropdown .bi.bi-bell");
    var attentionButton = document.querySelector("#navbarNav .badge.bg-danger");

    if (!navbarContainer || !navbarToggler || !mobileNav || !desktopReminderIcon) return;
    if (document.getElementById("mobileNotificationDropdown")) return;

    var reminderDropdown = desktopReminderIcon.closest(".nav-item.dropdown");
    var reminderMenu = reminderDropdown ? reminderDropdown.querySelector(".dropdown-menu") : null;
    if (!reminderMenu) return;

    var bottomReminderIcon = mobileNav.querySelector(".mobile-nav-item .bi-bell-fill");
    var bottomReminderLink = bottomReminderIcon ? bottomReminderIcon.closest("a.mobile-nav-item") : null;
    if (bottomReminderLink) bottomReminderLink.remove();

    var legacyAttentionBadge = mobileNav.querySelector(".mobile-nav-badge, .mobile-nav-item .badge");
    if (legacyAttentionBadge) legacyAttentionBadge.remove();

    var attentionCount = attentionButton ? attentionButton.textContent.trim() : "";
    var attentionMenu = attentionButton ? attentionButton.closest(".dropdown").querySelector(".dropdown-menu") : null;

    var actions = document.createElement("div");
    actions.className = "mobile-header-actions d-lg-none";

    var dropdown = document.createElement("div");
    dropdown.className = "dropdown";

    var button = document.createElement("button");
    button.id = "mobileNotificationDropdown";
    button.type = "button";
    button.className = "mobile-header-notification-button";
    button.setAttribute("data-bs-toggle", "dropdown");
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", "Уведомления и напоминания");
    button.setAttribute("title", "Уведомления и напоминания");
    button.innerHTML = '<i class="bi bi-bell-fill" aria-hidden="true"></i>';

    if (attentionCount) {
      var badge = document.createElement("span");
      badge.className = "mobile-header-notification-badge";
      badge.textContent = attentionCount;
      button.appendChild(badge);
    }

    var menu = document.createElement("ul");
    menu.className = "dropdown-menu dropdown-menu-end shadow-sm mobile-notifications-menu";
    menu.setAttribute("aria-labelledby", "mobileNotificationDropdown");

    if (copyMenuItems(attentionMenu, menu)) {
      var divider = document.createElement("li");
      divider.innerHTML = '<hr class="dropdown-divider">';
      menu.appendChild(divider);
    }

    copyMenuItems(reminderMenu, menu);

    dropdown.appendChild(button);
    dropdown.appendChild(menu);
    actions.appendChild(dropdown);
    navbarContainer.insertBefore(actions, navbarToggler);
  }

  function init() {
    var nodes = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < nodes.length; i++) {
      var button = nodes[i];
      toggles.push(button);
      button.addEventListener("click", function () {
        var nextTheme = currentTheme() === "dark" ? "light" : "dark";
        applyTheme(nextTheme);
        safeSet(nextTheme);
      });
    }

    var storedTheme = safeGet();
    if (storedTheme) {
      applyTheme(storedTheme);
    } else if (mq && typeof mq.matches === "boolean") {
      applyTheme(mq.matches ? "dark" : "light");
    } else {
      applyTheme("light");
    }

    injectMobileStyles();
    setupMobileNotifications();

    if (mq) {
      var onSystemThemeChange = function (event) {
        if (!safeGet()) applyTheme(event.matches ? "dark" : "light");
      };

      if (typeof mq.addEventListener === "function") {
        mq.addEventListener("change", onSystemThemeChange);
      } else if (typeof mq.addListener === "function") {
        mq.addListener(onSystemThemeChange);
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

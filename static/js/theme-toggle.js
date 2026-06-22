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

  function applyTheme(theme) {
    theme = theme === "dark" ? "dark" : "light";
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

  function syncMobileNavbarHeight() {
    var navbar = document.querySelector(".theme-navbar");
    if (!navbar) return;
    docEl.style.setProperty("--mobile-navbar-height", Math.ceil(navbar.getBoundingClientRect().height) + "px");
  }

  function addMobileNavigationStyles() {
    if (document.getElementById("mobile-navigation-styles")) return;

    var style = document.createElement("style");
    style.id = "mobile-navigation-styles";
    style.textContent = [
      "@media (max-width: 991.98px) {",
      "  .theme-navbar { position: relative; z-index: 1060; }",
      "  .theme-navbar .container { flex-wrap: nowrap; }",
      "  .theme-navbar .navbar-brand { min-width: 0; }",
      "  .theme-navbar .navbar-toggler { flex: 0 0 auto; }",
      "  .navbar-mobile-actions { display: flex; align-items: center; }",
      "  .navbar-mobile-actions > .dropdown { position: static; }",
      "  .navbar-mobile-notification-button { position: relative; display: inline-grid; place-items: center; width: 42px; height: 42px; color: var(--nav-fg); background: color-mix(in srgb, var(--surface) 82%, transparent); border: 1px solid var(--border); border-radius: 12px; }",
      "  .navbar-mobile-notification-button:hover, .navbar-mobile-notification-button:focus-visible { color: var(--brand-1); background: color-mix(in srgb, var(--brand-1) 10%, var(--surface)); border-color: color-mix(in srgb, var(--brand-1) 44%, var(--border)); outline: none; }",
      "  .navbar-mobile-notification-button i { font-size: 1.18rem; }",
      "  .navbar-mobile-notification-badge { position: absolute; top: -.35rem; right: -.45rem; min-width: 1.25rem; height: 1.25rem; padding: 0 .3rem; display: inline-flex; align-items: center; justify-content: center; color: #fff; background: #dc3545; border: 2px solid var(--nav-bg); border-radius: 999px; font-size: .65rem; font-weight: 700; line-height: 1; }",
      "  .mobile-notifications-menu.show { position: fixed !important; top: calc(var(--mobile-navbar-height, 6rem) + .5rem) !important; left: .75rem !important; right: .75rem !important; width: auto !important; max-width: none !important; max-height: calc(100dvh - var(--mobile-navbar-height, 6rem) - 1.25rem); margin: 0 !important; padding: .35rem 0; overflow-y: auto; transform: none !important; z-index: 1080; }",
      "  .mobile-notifications-menu .dropdown-header { padding: .6rem .9rem .35rem; white-space: normal; }",
      "  .mobile-notifications-menu .dropdown-item { display: flex; align-items: flex-start !important; gap: .7rem; padding: .7rem .9rem; white-space: normal; overflow-wrap: anywhere; line-height: 1.25; }",
      "  .mobile-notifications-menu .dropdown-item > span:first-child { min-width: 0; flex: 1 1 auto; }",
      "  .mobile-notifications-menu .dropdown-item .badge { flex: 0 0 auto; margin-top: .05rem; }",
      "  /* The bottom bar already exposes Clients and New. Reminders live in the bell. */",
      "  #navbarNav > .navbar-nav.me-auto > .nav-item:nth-child(1),",
      "  #navbarNav > .navbar-nav.me-auto > .nav-item:nth-child(2),",
      "  #navbarNav > .navbar-nav.me-auto > .nav-item:nth-child(4) { display: none; }",
      "  .theme-navbar .navbar-collapse { position: fixed; top: calc(var(--mobile-navbar-height, 6rem) + .5rem); left: .75rem; right: .75rem; width: auto; max-height: calc(100dvh - var(--mobile-navbar-height, 6rem) - 1.25rem); overflow-y: auto; padding: .65rem; background: var(--nav-bg); border: 1px solid var(--border); border-radius: 18px; box-shadow: 0 18px 42px rgba(0, 0, 0, .28); }",
      "  .theme-navbar .navbar-collapse:not(.show) { display: none; }",
      "  .theme-navbar .navbar-collapse.show { display: block; }",
      "  .theme-navbar .navbar-nav { gap: .2rem; margin: 0 !important; }",
      "  .theme-navbar .navbar-nav + .navbar-nav { margin-top: .5rem !important; padding-top: .55rem; border-top: 1px solid var(--border); }",
      "  .theme-navbar .nav-link, .theme-navbar .navbar-collapse .theme-toggle, .theme-navbar .navbar-collapse [data-language-switcher] { width: 100%; min-height: 44px; }",
      "  .theme-navbar .nav-link { display: flex; align-items: center; padding: .68rem .75rem; border-radius: 12px; white-space: normal; }",
      "  .theme-navbar .navbar-collapse .nav-item { margin: 0 !important; }",
      "  .theme-navbar .navbar-collapse .dropdown-menu { position: static !important; width: 100%; margin: .2rem 0 .5rem; transform: none !important; box-shadow: none; }",
      "  .theme-navbar .navbar-collapse .dropdown-item { white-space: normal; }",
      "  .theme-navbar .navbar-collapse [data-language-switcher] { display: flex; align-items: center; }",
      "  .theme-navbar .navbar-collapse [data-language-switcher] .form-select { width: 100%; }",
      "  .mobile-nav-bar { box-sizing: border-box; height: calc(62px + env(safe-area-inset-bottom)); justify-content: center; gap: .25rem; padding: .2rem .5rem calc(.2rem + env(safe-area-inset-bottom)); }",
      "  .mobile-nav-bar > .mobile-nav-item, .mobile-nav-bar > .dropup { flex: 0 1 80px !important; min-width: 0; }",
      "  .mobile-nav-bar > .dropup .mobile-nav-item { width: 100%; }",
      "  .mobile-nav-item { flex: 0 1 80px; min-width: 0; padding: .22rem .1rem; font-size: .68rem; line-height: 1.15; }",
      "  .mobile-nav-item i { font-size: 1.22rem; margin-bottom: .05rem; }",
      "  body { padding-bottom: calc(72px + env(safe-area-inset-bottom)) !important; }",
      "}"
    ].join("\n");

    document.head.appendChild(style);
  }

  function copyMenuItems(source, target) {
    if (!source) return false;

    var items = source.children;
    var copied = false;
    for (var i = 0; i < items.length; i++) {
      target.appendChild(items[i].cloneNode(true));
      copied = true;
    }
    return copied;
  }

  function setupMobileNotifications() {
    var container = document.querySelector(".theme-navbar .container");
    var toggler = document.querySelector(".theme-navbar .navbar-toggler");
    var mobileNav = document.querySelector(".mobile-nav-bar");
    var desktopBell = document.querySelector("#navbarNav .nav-item.dropdown .bi.bi-bell");

    if (!container || !toggler || !mobileNav || !desktopBell || document.getElementById("mobileNotificationDropdown")) {
      return;
    }

    var desktopDropdown = desktopBell.closest(".nav-item.dropdown");
    var reminderMenu = desktopDropdown ? desktopDropdown.querySelector(".dropdown-menu") : null;
    if (!reminderMenu) return;

    var bottomBell = mobileNav.querySelector(".mobile-nav-item .bi-bell-fill");
    var bottomReminder = bottomBell ? bottomBell.closest("a.mobile-nav-item") : null;
    if (bottomReminder) bottomReminder.remove();

    var oldBadge = mobileNav.querySelector(".mobile-nav-item .badge");
    var count = oldBadge ? oldBadge.textContent.trim() : "";
    if (oldBadge) oldBadge.remove();

    var actions = document.createElement("div");
    actions.className = "navbar-mobile-actions d-lg-none ms-auto me-2";

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

    if (count) {
      var badge = document.createElement("span");
      badge.className = "navbar-mobile-notification-badge";
      badge.textContent = count;
      button.appendChild(badge);
    }

    var menu = document.createElement("ul");
    menu.className = "dropdown-menu dropdown-menu-end shadow-sm mobile-notifications-menu";
    menu.setAttribute("aria-labelledby", "mobileNotificationDropdown");

    var attentionButton = document.querySelector("#navbarNav .badge.bg-danger");
    var attentionMenu = attentionButton ? attentionButton.closest(".dropdown").querySelector(".dropdown-menu") : null;
    if (copyMenuItems(attentionMenu, menu)) {
      var divider = document.createElement("li");
      divider.innerHTML = '<hr class="dropdown-divider">';
      menu.appendChild(divider);
    }

    copyMenuItems(reminderMenu, menu);

    dropdown.appendChild(button);
    dropdown.appendChild(menu);
    actions.appendChild(dropdown);
    container.insertBefore(actions, toggler);
  }

  function init() {
    var nodes = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < nodes.length; i++) {
      toggles.push(nodes[i]);
      nodes[i].addEventListener("click", function () {
        var next = currentTheme() === "dark" ? "light" : "dark";
        applyTheme(next);
        safeSet(next);
      });
    }

    var stored = safeGet();
    applyTheme(stored || (mq && mq.matches ? "dark" : "light"));
    syncMobileNavbarHeight();
    addMobileNavigationStyles();
    setupMobileNotifications();

    window.addEventListener("resize", syncMobileNavbarHeight);

    if (mq) {
      var systemChange = function (event) {
        if (!safeGet()) applyTheme(event.matches ? "dark" : "light");
      };
      if (mq.addEventListener) mq.addEventListener("change", systemChange);
      else if (mq.addListener) mq.addListener(systemChange);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

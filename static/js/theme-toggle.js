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

  function safeGet() { try { return localStorage.getItem(STORAGE_KEY); } catch (_) { return null; } }
  function safeSet(value) { try { localStorage.setItem(STORAGE_KEY, value); } catch (_) {} }
  function currentTheme() { return docEl.getAttribute("data-theme") === "dark" ? "dark" : "light"; }

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
      if (label) label.textContent = theme === "dark" ? button.dataset.themeDarkText : button.dataset.themeLightText;
    }
  }

  function addMobileStyles() {
    if (document.getElementById("mobile-notification-nav-styles")) return;
    var style = document.createElement("style");
    style.id = "mobile-notification-nav-styles";
    style.textContent = "@media (max-width:991.98px){"
      + ".navbar-mobile-actions{display:flex;align-items:center}.navbar-mobile-notification-button{position:relative;display:inline-grid;place-items:center;width:42px;height:42px;color:var(--nav-fg);background:color-mix(in srgb,var(--surface) 82%,transparent);border:1px solid var(--border);border-radius:12px}.navbar-mobile-notification-button i{font-size:1.18rem}.navbar-mobile-notification-badge{position:absolute;top:-.35rem;right:-.45rem;min-width:1.25rem;height:1.25rem;padding:0 .3rem;display:inline-flex;align-items:center;justify-content:center;color:#fff;background:#dc3545;border:2px solid var(--nav-bg);border-radius:999px;font-size:.65rem;font-weight:700;line-height:1}.mobile-notifications-menu{min-width:min(21rem,calc(100vw - 2rem));max-height:min(70vh,30rem);overflow-y:auto}.theme-navbar .container{flex-wrap:nowrap}.theme-navbar .navbar-brand{min-width:0}.theme-navbar .navbar-toggler{flex:0 0 auto}.mobile-nav-bar{justify-content:space-evenly}"
      + "}";
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
    if (!container || !toggler || !mobileNav || !desktopBell || document.getElementById("mobileNotificationDropdown")) return;

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
      var separator = document.createElement("li");
      separator.innerHTML = '<hr class="dropdown-divider">';
      menu.appendChild(separator);
    }
    copyMenuItems(reminderMenu, menu);

    dropdown.appendChild(button);
    dropdown.appendChild(menu);
    actions.appendChild(dropdown);
    container.insertBefore(actions, toggler);
    addMobileStyles();
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
    setupMobileNotifications();

    if (mq) {
      var systemChange = function (event) { if (!safeGet()) applyTheme(event.matches ? "dark" : "light"); };
      if (mq.addEventListener) mq.addEventListener("change", systemChange);
      else if (mq.addListener) mq.addListener(systemChange);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

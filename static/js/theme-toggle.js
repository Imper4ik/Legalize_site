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

  function init() {
    // соберём все кнопки
    var nodes = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < nodes.length; i++) setupToggle(nodes[i]);

    // первичная установка: сохранённое → системное → light
    var stored = safeGet();
    if (stored) apply(stored);
    else if (mq && typeof mq.matches === "boolean") apply(mq.matches ? "dark" : "light");
    else apply("light");

    // слушаем смену системной темы, если пользователь не переопределил
    if (mq) {
      if (typeof mq.addEventListener === "function") mq.addEventListener("change", handleSystemChange);
      else if (typeof mq.addListener === "function") mq.addListener(handleSystemChange);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

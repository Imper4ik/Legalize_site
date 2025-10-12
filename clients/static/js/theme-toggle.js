  (function () {
  if (typeof window !== 'undefined') {
    if (window.__themeToggleInitialized) {
      return;
    }

    window.__themeToggleInitialized = true;
  }

  const storageKey = 'preferredTheme';
  const toggles = [];

  const getStoredTheme = () => {
    try {
      return localStorage.getItem(storageKey);
    } catch (error) {
      return null;
    }
  };

  const saveTheme = (theme) => {
    try {
      localStorage.setItem(storageKey, theme);
    } catch (error) {
      // Ignore storage write errors (e.g. private mode)
    }
  };

  const prefersDarkQuery = window.matchMedia
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null;

  const getPreferredTheme = () => {
    const storedTheme = getStoredTheme();
    if (storedTheme) {
      return storedTheme;
    }

    if (prefersDarkQuery && typeof prefersDarkQuery.matches === 'boolean') {
      return prefersDarkQuery.matches ? 'dark' : 'light';
    }

    return 'light';
  };

  const updateToggle = (toggle, theme) => {
    toggle.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');

    const textElement = toggle.querySelector('[data-theme-toggle-text]');
    if (textElement) {
      const textContent =
        theme === 'dark'
          ? toggle.dataset.themeDarkText
          : toggle.dataset.themeLightText;
      if (textContent) {
        textElement.textContent = textContent;
      }
    }

    const title =
      theme === 'dark'
        ? toggle.dataset.themeDarkTitle
        : toggle.dataset.themeLightTitle;

    if (title) {
      toggle.setAttribute('title', title);
    }

    const label =
      theme === 'dark'
        ? toggle.dataset.themeDarkLabel
        : toggle.dataset.themeLightLabel;

    if (label) {
      toggle.setAttribute('aria-label', label);
    }
  };

  const applyTheme = (theme) => {
    document.documentElement.setAttribute('data-bs-theme', theme);
    toggles.forEach((toggle) => updateToggle(toggle, theme));
  };

  const setupToggle = (toggle) => {
    toggles.push(toggle);

    toggle.addEventListener('click', () => {
      const currentTheme = document.documentElement.getAttribute('data-bs-theme');
      const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
      applyTheme(nextTheme);
      saveTheme(nextTheme);
    });
  };

  const handleSystemPreferenceChange = (event) => {
    const storedTheme = getStoredTheme();
    if (!storedTheme) {
      applyTheme(event.matches ? 'dark' : 'light');
    }
  };

  const init = () => {
    document
      .querySelectorAll('[data-theme-toggle]')
      .forEach((toggle) => setupToggle(toggle));

    const themeFromDom = document.documentElement.getAttribute('data-bs-theme');
    const initialTheme = themeFromDom || getPreferredTheme();
    applyTheme(initialTheme);

    if (prefersDarkQuery) {
      if (typeof prefersDarkQuery.addEventListener === 'function') {
        prefersDarkQuery.addEventListener('change', handleSystemPreferenceChange);
      } else if (typeof prefersDarkQuery.addListener === 'function') {
        prefersDarkQuery.addListener(handleSystemPreferenceChange);
      }
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

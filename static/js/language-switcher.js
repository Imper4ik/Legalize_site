(function () {
  const supportedLanguages = ['ru', 'pl', 'en'];
  const prefixPattern = new RegExp(`^/(?:${supportedLanguages.join('|')})(/|$)`);

  const buildNextPath = (lang) => {
    if (!supportedLanguages.includes(lang)) {
      const { pathname, search } = window.location;
      return `${pathname}${search || ''}`;
    }

    const { pathname, search } = window.location;
    const basePath = pathname.replace(prefixPattern, '/');
    const normalizedBase = basePath.startsWith('/') ? basePath : `/${basePath}`;
    const withPrefix = `/${lang}${normalizedBase}`.replace(/\/{2,}/g, '/');
    return `${withPrefix}${search || ''}`;
  };

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-language-switcher]').forEach((form) => {
      const select = form.querySelector('select[name="language"]');
      const nextInput = form.querySelector('input[name="next"]');

      if (!select || !nextInput) {
        return;
      }

      select.addEventListener('change', (event) => {
        const nextPath = buildNextPath(event.target.value);
        nextInput.value = nextPath;
        form.submit();
      });
    });
  });
})();

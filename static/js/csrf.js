(function () {
  function getCookie(name) {
    const value = document.cookie
      .split(';')
      .map((cookie) => cookie.trim())
      .find((cookie) => cookie.startsWith(`${name}=`));
    if (!value) {
      return null;
    }
    return decodeURIComponent(value.split('=')[1]);
  }

  function getCsrfToken() {
    return (
      getCookie('csrftoken') ||
      (document.querySelector('meta[name="csrf-token"]') || {}).content ||
      null
    );
  }

  const csrfSafeMethods = ['GET', 'HEAD', 'OPTIONS', 'TRACE'];
  const originalFetch = window.fetch;

  window.fetch = function patchedFetch(input, init = {}) {
    const options = typeof init === 'object' ? { ...init } : {};
    const request = new Request(input, options);
    const method = (options.method || request.method || 'GET').toUpperCase();

    if (!csrfSafeMethods.includes(method) && request.url.startsWith(window.location.origin)) {
      const headers = new Headers(options.headers || request.headers || {});
      if (!headers.has('X-CSRFToken')) {
        const token = getCsrfToken();
        if (token) {
          headers.set('X-CSRFToken', token);
        }
      }
      options.headers = headers;
      return originalFetch(new Request(request, options));
    }

    return originalFetch(request, options);
  };
})();

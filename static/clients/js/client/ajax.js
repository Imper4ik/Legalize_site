function createTemplateFragment(html) {
  const template = document.createElement('template');
  template.innerHTML = html.trim();
  return template.content;
}

function replaceNodeContents(node, html) {
  if (!node || !html) {
    return;
  }

  node.replaceChildren(createTemplateFragment(html));
}

function buildAjaxHeaders(headers, accept = 'application/json') {
  const merged = new Headers(headers || {});
  if (!merged.has('X-Requested-With')) {
    merged.set('X-Requested-With', 'XMLHttpRequest');
  }
  if (accept && !merged.has('Accept')) {
    merged.set('Accept', accept);
  }
  return merged;
}

function buildAjaxOptions(options = {}, accept = 'application/json') {
  return {
    credentials: 'same-origin',
    ...options,
    headers: buildAjaxHeaders(options.headers, accept),
  };
}

function normalizeResponsePreview(text) {
  return (text || '').replace(/\s+/g, ' ').trim().slice(0, 240);
}

function buildResponseError(message, details = {}) {
  const error = new Error(message);
  Object.assign(error, details);
  return error;
}

async function readJsonPayload(response) {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.toLowerCase().includes('application/json')) {
    const responseText = normalizeResponsePreview(await response.text());
    throw buildResponseError(`Expected JSON response but received ${contentType || 'unknown content type'}`, {
      responseStatus: response.status,
      contentType,
      responseText,
    });
  }

  try {
    return await response.json();
  } catch (error) {
    throw buildResponseError('Failed to parse JSON response', {
      cause: error,
      responseStatus: response.status,
      contentType,
    });
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, buildAjaxOptions(options));
  const data = await readJsonPayload(response);
  return { response, data };
}

async function fetchHtml(url, options = {}) {
  const response = await fetch(url, buildAjaxOptions(options, 'text/html, */*; q=0.01'));
  if (!response.ok) {
    const responseText = normalizeResponsePreview(await response.text());
    throw buildResponseError(`HTTP ${response.status}`, {
      responseStatus: response.status,
      contentType: response.headers.get('content-type') || '',
      responseText,
    });
  }

  const contentType = response.headers.get('content-type') || '';
  if (contentType.toLowerCase().includes('application/json')) {
    const data = await readJsonPayload(response);
    throw buildResponseError('Expected HTML response but received JSON', {
      responseStatus: response.status,
      contentType,
      data,
    });
  }

  return { response, html: await response.text() };
}

function logAjaxError(context, error, extra = {}) {
  console.error(`[client_detail] ${context}`, {
    message: error?.message || String(error),
    responseStatus: error?.responseStatus,
    contentType: error?.contentType,
    responseText: error?.responseText,
    ...extra,
    error,
  });
}
function showAlert(containerId, message, type = 'success') {
  const container = document.getElementById(containerId);
  if (!container || !message) {
    return;
  }

  const alert = document.createElement('div');
  alert.className = `alert alert-${type} alert-dismissible fade show`;
  alert.role = 'alert';
  alert.textContent = message;

  const closeButton = document.createElement('button');
  closeButton.type = 'button';
  closeButton.className = 'btn-close';
  closeButton.setAttribute('data-bs-dismiss', 'alert');
  closeButton.setAttribute('aria-label', 'Close');
  alert.appendChild(closeButton);

  container.append(alert);

  window.setTimeout(() => {
    bootstrap.Alert.getOrCreateInstance(alert).close();
  }, 3500);
}

function showPaymentAlert(message, type = 'success') {
  showAlert('payment-alerts', message, type);
}

function showDocumentAlert(message, type = 'success') {
  showAlert('document-alerts', message, type);
}
function getErrorMessage(errors, fallbackMessage = 'Operation failed. Please try again.') {
  if (!errors) {
    return fallbackMessage;
  }

  if (typeof errors === 'string') {
    return errors;
  }

  const firstField = Object.values(errors)[0];
  if (Array.isArray(firstField) && firstField.length > 0) {
    return firstField[0];
  }

  return fallbackMessage;
}

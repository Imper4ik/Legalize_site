(function () {
  let refreshChecklist = null;
  let pauseChecklistRefreshUntil = 0;

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

  function pauseChecklistRefresh(duration = 3000) {
    pauseChecklistRefreshUntil = Math.max(pauseChecklistRefreshUntil, Date.now() + duration);
  }

  function initPriceAutoFill() {
    const addPaymentModal = document.getElementById('addPaymentModal');
    if (!addPaymentModal) {
      return;
    }

    const template = addPaymentModal.dataset.priceUrlTemplate;
    const serviceSelect = addPaymentModal.querySelector('#id_service_description');
    const priceInput = addPaymentModal.querySelector('#id_total_amount');
    if (!template || !serviceSelect || !priceInput) {
      return;
    }

    let controller = null;

    async function requestPrice(service) {
      if (!service) {
        priceInput.value = '0.00';
        return;
      }

      if (controller) {
        controller.abort();
      }
      controller = new AbortController();

      try {
        const { data } = await fetchJson(template.replace('__service__', encodeURIComponent(service)), {
          signal: controller.signal,
        });
        if (Object.prototype.hasOwnProperty.call(data, 'price')) {
          const price = Number.parseFloat(data.price);
          priceInput.value = Number.isFinite(price) ? price.toFixed(2) : '0.00';
        }
      } catch (error) {
        if (error.name !== 'AbortError') {
          logAjaxError('request price', error, { template });
        }
      }
    }

    serviceSelect.addEventListener('change', (event) => {
      requestPrice(event.target.value);
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

  function prependPaymentItem(html, paymentId) {
    const list = document.getElementById('payment-list-container');
    if (!list || !html) {
      return;
    }

    const newItem = document.createElement('li');
    newItem.className = 'list-group-item';
    newItem.dataset.paymentId = paymentId;
    replaceNodeContents(newItem, html);

    const emptyState = document.getElementById('no-payments-message');
    if (emptyState) {
      emptyState.remove();
    }

    list.prepend(newItem);
  }

  function updatePaymentItem(html, paymentId) {
    const list = document.getElementById('payment-list-container');
    if (!list || !html || !paymentId) {
      return;
    }

    const existing = list.querySelector(`[data-payment-id="${paymentId}"]`);
    if (existing) {
      replaceNodeContents(existing, html);
    }
  }

  function removePaymentItem(paymentId) {
    const list = document.getElementById('payment-list-container');
    if (!list || !paymentId) {
      return;
    }

    const existing = list.querySelector(`[data-payment-id="${paymentId}"]`);
    existing?.remove();

    if (!list.children.length) {
      const emptyState = document.createElement('li');
      emptyState.className = 'list-group-item text-muted';
      emptyState.id = 'no-payments-message';
      emptyState.textContent = list.dataset.emptyText || 'Счета на оплату ещё не созданы.';
      list.append(emptyState);
    }
  }

  function getErrorMessage(errors, fallbackMessage = 'Не удалось завершить операцию. Попробуйте ещё раз.') {
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

  function initAddPaymentForm() {
    const modal = document.getElementById('addPaymentModal');
    if (!modal) {
      return;
    }

    const form = modal.querySelector('form');
    if (!form) {
      return;
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submitButton = form.querySelector('[type="submit"]');
      submitButton?.setAttribute('disabled', 'disabled');

      try {
        const { response, data } = await fetchJson(form.action, {
          method: 'POST',
          body: new FormData(form),
        });

        if (response.ok && data.status === 'success' && data.html) {
          prependPaymentItem(data.html, data.payment_id);
          bootstrap.Modal.getOrCreateInstance(modal).hide();
          form.reset();
          showPaymentAlert('Платёж успешно добавлен.');
          return;
        }

        showPaymentAlert(
          getErrorMessage(data.errors || data.message, 'Не удалось создать платёж. Попробуйте ещё раз.'),
          'danger',
        );
      } catch (error) {
        logAjaxError('create payment', error, { url: form.action });
        showPaymentAlert('Не удалось создать платёж. Попробуйте ещё раз.', 'danger');
      } finally {
        submitButton?.removeAttribute('disabled');
      }
    });
  }

  function initEditPaymentModal() {
    const modal = document.getElementById('editPaymentModal');
    if (!modal) {
      return;
    }

    const form = modal.querySelector('#editPaymentForm');
    if (!form) {
      return;
    }

    function setFieldValue(name, value, fallback = '') {
      const field = form.elements.namedItem(name);
      if (!field) {
        return;
      }
      field.value = value || fallback;
    }

    modal.addEventListener('show.bs.modal', (event) => {
      const button = event.relatedTarget;
      if (!button) {
        return;
      }

      const action = button.getAttribute('data-form-action') || button.getAttribute('data-url');
      if (action) {
        form.setAttribute('action', action);
      }

      setFieldValue('service_description', button.dataset.service, '');
      setFieldValue('total_amount', button.dataset.totalAmount, '');
      setFieldValue('amount_paid', button.dataset.amountPaid, '0.00');
      setFieldValue('status', button.dataset.status, 'pending');
      setFieldValue('payment_method', button.dataset.paymentMethod, 'cash');
      setFieldValue('payment_date', button.dataset.paymentDate, '');
      setFieldValue('due_date', button.dataset.dueDate, '');
      setFieldValue('transaction_id', button.dataset.transactionId, '');
    });

    modal.addEventListener('hidden.bs.modal', () => {
      form.reset();
      form.removeAttribute('action');
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submitButton = form.querySelector('[type="submit"]');
      submitButton?.setAttribute('disabled', 'disabled');

      try {
        const { response, data } = await fetchJson(form.action, {
          method: 'POST',
          body: new FormData(form),
        });

        if (response.ok && data.status === 'success' && data.html && data.payment_id) {
          updatePaymentItem(data.html, data.payment_id);
          bootstrap.Modal.getOrCreateInstance(modal).hide();
          showPaymentAlert('Платёж успешно обновлён.');
          return;
        }

        showPaymentAlert(
          getErrorMessage(data.errors || data.message, 'Не удалось обновить платёж. Попробуйте ещё раз.'),
          'danger',
        );
      } catch (error) {
        logAjaxError('edit payment', error, { url: form.action });
        showPaymentAlert('Не удалось обновить платёж. Попробуйте ещё раз.', 'danger');
      } finally {
        submitButton?.removeAttribute('disabled');
      }
    });
  }

  function initPaymentDeletion() {
    const list = document.getElementById('payment-list-container');
    if (!list) {
      return;
    }

    list.addEventListener('click', async (event) => {
      const button = event.target.closest('.delete-payment-button');
      if (!button) {
        return;
      }

      const form = button.closest('form');
      const item = button.closest('[data-payment-id]');
      const paymentId = item?.dataset.paymentId;
      if (!(form instanceof HTMLFormElement) || !form.classList.contains('delete-payment-form') || !paymentId) {
        return;
      }

      event.preventDefault();
      button.setAttribute('disabled', 'disabled');

      try {
        const { response, data } = await fetchJson(form.action, {
          method: 'POST',
          body: new FormData(form),
        });

        if (response.ok && data.status === 'success') {
          removePaymentItem(paymentId);
          showPaymentAlert(data.message || 'Платёж успешно удалён.');
          return;
        }

        showPaymentAlert(
          getErrorMessage(data.errors || data.message, 'Не удалось удалить платёж. Попробуйте ещё раз.'),
          'danger',
        );
      } catch (error) {
        logAjaxError('delete payment', error, { url: form.action, paymentId });
        showPaymentAlert('Не удалось удалить платёж. Попробуйте ещё раз.', 'danger');
      } finally {
        button.removeAttribute('disabled');
      }
    });
  }

  function initDocumentUploadModal() {
    const modal = document.getElementById('uploadDocumentModal');
    if (!modal) {
      return;
    }

    const description = modal.querySelector('#uploadDocumentDescription');
    const form = modal.querySelector('form');
    const actionTemplate = modal.dataset.actionTemplate;
    const confirmTemplate = modal.dataset.confirmUrlTemplate;
    const parseInput = modal.querySelector('#uploadDocumentParseWezwanie');
    const confirmStep = modal.querySelector('#wezwanieConfirmationStep');
    const confirmActions = modal.querySelector('#wezwanieConfirmActions');
    const uploadActions = modal.querySelector('#uploadDocumentActions');
    const confirmButton = modal.querySelector('#wezwanieConfirmButton');
    const parsedFirstName = modal.querySelector('#wezwanieParsedFirstName');
    const parsedLastName = modal.querySelector('#wezwanieParsedLastName');
    const parsedCaseNumber = modal.querySelector('#wezwanieParsedCaseNumber');
    const parsedFingerprintsDate = modal.querySelector('#wezwanieParsedFingerprintsDate');
    const parsedFingerprintsTime = modal.querySelector('#wezwanieParsedFingerprintsTime');
    const parsedFingerprintsLocation = modal.querySelector('#wezwanieParsedFingerprintsLocation');
    const parsedDecisionDate = modal.querySelector('#wezwanieParsedDecisionDate');

    if (!form) {
      return;
    }

    const submitButton = form.querySelector('#uploadDocumentSubmitButton');
    const parseButton = form.querySelector('#wezwanieParseButton');

    function resetConfirmation() {
      confirmStep?.classList.add('d-none');
      confirmActions?.classList.add('d-none');
      uploadActions?.classList.remove('d-none');
      if (parsedFirstName) parsedFirstName.value = '';
      if (parsedLastName) parsedLastName.value = '';
      if (parsedCaseNumber) parsedCaseNumber.value = '';
      if (parsedFingerprintsDate) parsedFingerprintsDate.value = '';
      if (parsedFingerprintsTime) parsedFingerprintsTime.value = '';
      if (parsedFingerprintsLocation) parsedFingerprintsLocation.value = '';
      if (parsedDecisionDate) parsedDecisionDate.value = '';
      if (confirmButton) {
        confirmButton.dataset.confirmUrl = '';
      }
    }

    modal.addEventListener('show.bs.modal', (event) => {
      const button = event.relatedTarget;
      if (!button || !form || !actionTemplate) {
        return;
      }

      const docType = button.getAttribute('data-doc-type');
      const docName = button.getAttribute('data-doc-name');

      if (docType) {
        form.setAttribute('action', actionTemplate.replace('__doc_type__', encodeURIComponent(docType)));
      }

      if (description) {
        description.textContent = docName ? `Вы загружаете документ: "${docName}"` : '';
      }

      const isWezwanie = docType === 'wezwanie';
      if (parseInput) {
        parseInput.value = isWezwanie ? '1' : '0';
      }

      if (parseButton && submitButton) {
        parseButton.classList.toggle('d-none', !isWezwanie);
        submitButton.classList.toggle('d-none', isWezwanie);
      }

      resetConfirmation();
    });

    modal.addEventListener('hidden.bs.modal', () => {
      form.reset();
      if (description) {
        description.textContent = '';
      }
      resetConfirmation();
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      submitButton?.setAttribute('disabled', 'disabled');
      parseButton?.setAttribute('disabled', 'disabled');
      pauseChecklistRefresh();

      try {
        const { response, data } = await fetchJson(form.action, {
          method: 'POST',
          body: new FormData(form),
        });

        if (response.ok && data.status === 'success') {
          if (data.pending_confirmation && confirmStep && confirmActions && uploadActions) {
            const parsed = data.parsed || {};
            if (parsedFirstName) parsedFirstName.value = parsed.first_name || '';
            if (parsedLastName) parsedLastName.value = parsed.last_name || '';
            if (parsedCaseNumber) parsedCaseNumber.value = parsed.case_number || '';
            if (parsedFingerprintsDate) parsedFingerprintsDate.value = parsed.fingerprints_date || '';
            if (parsedFingerprintsTime) parsedFingerprintsTime.value = parsed.fingerprints_time || '';
            if (parsedFingerprintsLocation) parsedFingerprintsLocation.value = parsed.fingerprints_location || '';
            if (parsedDecisionDate) parsedDecisionDate.value = parsed.decision_date || '';

            const rawTextarea = modal.querySelector('#wezwanieRawText');
            const rawTextContainer = modal.querySelector('#wezwanieRawTextContainer');
            const toggleRawBtn = modal.querySelector('#wezwanieToggleRawText');

            if (rawTextarea) {
              rawTextarea.value = parsed.raw_text || '';
            }
            if (rawTextContainer) {
              rawTextContainer.classList.add('d-none');
            }

            if (toggleRawBtn) {
              toggleRawBtn.onclick = () => {
                if (rawTextContainer) {
                  rawTextContainer.classList.toggle('d-none');
                }
              };
            }

            confirmStep.classList.remove('d-none');
            confirmActions.classList.remove('d-none');
            uploadActions.classList.add('d-none');

            if (confirmButton) {
              const confirmUrl = data.confirm_url
                || (confirmTemplate || '')
                  .replace('__doc_id__', data.doc_id)
                  .replace('/0/', `/${data.doc_id}/`);
              confirmButton.dataset.confirmUrl = confirmUrl;
            }
            return;
          }

          bootstrap.Modal.getOrCreateInstance(modal).hide();
          showDocumentAlert(data.message || 'Документ успешно добавлен.');
          if (typeof refreshChecklist === 'function') {
            await refreshChecklist({ force: true });
          } else {
            window.location.reload();
          }
          return;
        }

        showDocumentAlert(
          getErrorMessage(data.errors || data.message, 'Не удалось загрузить документ. Попробуйте ещё раз.'),
          'danger',
        );
      } catch (error) {
        logAjaxError('upload document', error, { url: form.action });
        showDocumentAlert('Не удалось загрузить документ. Попробуйте ещё раз.', 'danger');
      } finally {
        submitButton?.removeAttribute('disabled');
        parseButton?.removeAttribute('disabled');
      }
    });

    confirmButton?.addEventListener('click', async () => {
      const confirmUrl = confirmButton.dataset.confirmUrl;
      if (!confirmUrl) {
        return;
      }

      confirmButton.setAttribute('disabled', 'disabled');
      pauseChecklistRefresh();

      const payload = new FormData();
      payload.append('first_name', parsedFirstName?.value || '');
      payload.append('last_name', parsedLastName?.value || '');
      payload.append('case_number', parsedCaseNumber?.value || '');
      payload.append('fingerprints_date', parsedFingerprintsDate?.value || '');
      payload.append('decision_date', parsedDecisionDate?.value || '');

      try {
        const { response, data } = await fetchJson(confirmUrl, {
          method: 'POST',
          body: payload,
        });

        if (response.ok && data.status === 'success') {
          bootstrap.Modal.getOrCreateInstance(modal).hide();
          showDocumentAlert(data.message || 'Данные wezwanie подтверждены.');
          if (typeof refreshChecklist === 'function') {
            await refreshChecklist({ force: true });
          } else {
            window.location.reload();
          }
          return;
        }

        showDocumentAlert(
          getErrorMessage(data.errors || data.message, 'Не удалось подтвердить данные wezwanie.'),
          'danger',
        );
      } catch (error) {
        logAjaxError('confirm wezwanie', error, { url: confirmUrl });
        showDocumentAlert('Не удалось подтвердить данные wezwanie.', 'danger');
      } finally {
        confirmButton.removeAttribute('disabled');
      }
    });
  }

  function initChecklistRefresher() {
    const accordion = document.getElementById('documentAccordion');
    if (!accordion) {
      return;
    }

    const refreshUrl = accordion.dataset.refreshUrl;
    if (!refreshUrl) {
      return;
    }

    let controller = null;
    let isFetching = false;

    function restoreExpandedPanels(ids) {
      ids.forEach((id) => {
        const collapseEl = accordion.querySelector(`#${id}`);
        if (!collapseEl) {
          return;
        }
        const instance = bootstrap.Collapse.getOrCreateInstance(collapseEl, { toggle: false });
        instance.show();
        const trigger = accordion.querySelector(`[data-bs-target="#${id}"]`);
        if (trigger) {
          trigger.classList.remove('collapsed');
          trigger.setAttribute('aria-expanded', 'true');
        }
      });
    }

    async function refresh({ force = false } = {}) {
      const hasOpenModal = Boolean(document.querySelector('.modal.show'));
      const isUserInteracting = accordion.contains(document.activeElement);
      if (
        !force
        && (isFetching
          || document.visibilityState !== 'visible'
          || hasOpenModal
          || isUserInteracting
          || Date.now() < pauseChecklistRefreshUntil)
      ) {
        return;
      }

      const expanded = Array.from(accordion.querySelectorAll('.accordion-collapse.show')).map((panel) => panel.id);

      if (controller) {
        controller.abort();
      }
      controller = new AbortController();
      isFetching = true;

      try {
        const { html } = await fetchHtml(refreshUrl, {
          cache: 'no-store',
          signal: controller.signal,
        });
        const trimmedHtml = html.trim();
        if (!trimmedHtml || accordion.innerHTML.trim() === trimmedHtml) {
          return;
        }

        replaceNodeContents(accordion, trimmedHtml);
        restoreExpandedPanels(expanded);
      } catch (error) {
        if (error.name !== 'AbortError') {
          logAjaxError('refresh checklist', error, { url: refreshUrl });
        }
      } finally {
        isFetching = false;
      }
    }

    refreshChecklist = refresh;

    let intervalId = null;

    function startInterval() {
      if (intervalId === null) {
        intervalId = window.setInterval(refresh, 8000);
      }
    }

    function stopInterval() {
      if (intervalId !== null) {
        window.clearInterval(intervalId);
        intervalId = null;
      }
      if (controller) {
        controller.abort();
      }
    }

    document.addEventListener('show.bs.modal', stopInterval);
    document.addEventListener('hidden.bs.modal', () => {
      if (!document.querySelector('.modal.show')) {
        startInterval();
      }
    });

    document.addEventListener('visibilitychange', refresh);
    accordion.addEventListener('focusin', () => pauseChecklistRefresh(1500));
    accordion.addEventListener('pointerdown', () => pauseChecklistRefresh(1500));
    window.addEventListener('beforeunload', () => {
      stopInterval();
      document.removeEventListener('show.bs.modal', stopInterval);
    });

    startInterval();
    refresh();
  }

  function initDocumentDeletion() {
    const accordion = document.getElementById('documentAccordion');
    if (!accordion) {
      return;
    }

    accordion.addEventListener('click', async (event) => {
      const button = event.target.closest('.delete-document-button');
      if (!button) {
        return;
      }

      const form = button.closest('form');
      if (!(form instanceof HTMLFormElement) || !form.classList.contains('delete-document-form')) {
        return;
      }

      event.preventDefault();
      button.setAttribute('disabled', 'disabled');
      pauseChecklistRefresh();

      try {
        const { response, data } = await fetchJson(form.action, {
          method: 'POST',
          body: new FormData(form),
        });

        if (response.ok && data.status === 'success') {
          showDocumentAlert(data.message || 'Документ удалён.');
          if (typeof refreshChecklist === 'function') {
            await refreshChecklist({ force: true });
          } else {
            window.location.reload();
          }
          return;
        }

        showDocumentAlert(
          getErrorMessage(data.errors || data.message, 'Не удалось удалить документ. Попробуйте ещё раз.'),
          'danger',
        );
      } catch (error) {
        logAjaxError('delete document', error, { url: form.action });
        showDocumentAlert('Не удалось удалить документ. Попробуйте ещё раз.', 'danger');
      } finally {
        button.removeAttribute('disabled');
      }
    });
  }

  function initDocumentVerification() {
    const accordion = document.getElementById('documentAccordion');
    if (!accordion) {
      return;
    }

    accordion.addEventListener('submit', async (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement) || !form.classList.contains('toggle-verification-form')) {
        return;
      }

      event.preventDefault();
      const button = form.querySelector('[type="submit"]');
      button?.setAttribute('disabled', 'disabled');
      pauseChecklistRefresh();

      try {
        const { response, data } = await fetchJson(form.action, {
          method: 'POST',
          body: new FormData(form),
        });

        if (response.ok && data.status === 'success') {
          const successMessage = data.emails_sent
            ? 'Статус документа обновлён. Письмо с недостающими документами отправлено.'
            : 'Статус документа обновлён.';
          showDocumentAlert(data.message || successMessage);
          if (typeof refreshChecklist === 'function') {
            await refreshChecklist({ force: true });
          } else {
            window.location.reload();
          }
          return;
        }

        showDocumentAlert(
          getErrorMessage(data.errors || data.message, 'Не удалось обновить статус документа. Попробуйте ещё раз.'),
          'danger',
        );
      } catch (error) {
        logAjaxError('toggle document verification', error, { url: form.action });
        showDocumentAlert('Не удалось обновить статус документа. Попробуйте ещё раз.', 'danger');
      } finally {
        button?.removeAttribute('disabled');
      }
    });
  }

  function initBulkVerification() {
    const form = document.getElementById('verify-all-documents-form');
    if (!form) {
      return;
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();

      const submitButton = form.querySelector('[type="submit"]');
      submitButton?.setAttribute('disabled', 'disabled');
      pauseChecklistRefresh();

      try {
        const { response, data } = await fetchJson(form.action, {
          method: 'POST',
          body: new FormData(form),
        });

        if (response.ok && data.status === 'success') {
          showDocumentAlert('Все загруженные документы отмечены как проверенные.');
          if (typeof refreshChecklist === 'function') {
            await refreshChecklist({ force: true });
          } else {
            window.location.reload();
          }
          return;
        }

        showDocumentAlert(
          getErrorMessage(data.errors || data.message, 'Не удалось обновить статус документов. Попробуйте ещё раз.'),
          'danger',
        );
      } catch (error) {
        logAjaxError('verify all documents', error, { url: form.action });
        showDocumentAlert('Не удалось обновить статус документов. Попробуйте ещё раз.', 'danger');
      } finally {
        submitButton?.removeAttribute('disabled');
      }
    });
  }

  function initHoverDropdowns() {
    const dropdowns = document.querySelectorAll('.hover-dropdown');
    dropdowns.forEach((dropdown) => {
      const toggle = dropdown.querySelector('.dropdown-toggle');
      const menu = dropdown.querySelector('.dropdown-menu');
      if (!toggle) {
        return;
      }

      const dropdownInstance = () => bootstrap.Dropdown.getOrCreateInstance(toggle);

      let hideTimeout;
      const showMenu = () => {
        clearTimeout(hideTimeout);
        dropdownInstance().show();
      };

      const scheduleHide = () => {
        clearTimeout(hideTimeout);
        hideTimeout = setTimeout(() => dropdownInstance().hide(), 120);
      };

      dropdown.addEventListener('mouseenter', showMenu);
      dropdown.addEventListener('mouseleave', scheduleHide);

      if (menu) {
        menu.addEventListener('mouseenter', showMenu);
        menu.addEventListener('mouseleave', scheduleHide);
      }
    });
  }

  function initSendEmailModal() {
    const modal = document.getElementById('sendEmailModal');
    if (!modal) {
      return;
    }

    const previewUrlTemplate = modal.dataset.previewUrl;
    const templateTypeSelect = modal.querySelector('#emailTemplateType');
    const languageSelect = modal.querySelector('#emailLanguage');
    const subjectInput = modal.querySelector('#emailSubject');
    const bodyInput = modal.querySelector('#emailBody');
    const sendButton = modal.querySelector('#sendEmailButton');
    const form = modal.querySelector('#sendEmailForm');

    if (!previewUrlTemplate || !templateTypeSelect || !languageSelect || !subjectInput || !bodyInput || !form) {
      return;
    }

    async function fetchPreview() {
      const templateType = templateTypeSelect.value;
      const language = languageSelect.value;

      if (templateType === 'custom') {
        subjectInput.value = '';
        bodyInput.value = '';
        return;
      }

      subjectInput.value = 'Загрузка...';
      bodyInput.value = 'Загрузка шаблона...';
      sendButton.setAttribute('disabled', 'disabled');

      try {
        const url = new URL(previewUrlTemplate, window.location.origin);
        url.searchParams.append('template_type', templateType);
        url.searchParams.append('language', language);

        const { response, data } = await fetchJson(url);
        if (response.ok) {
          subjectInput.value = data.subject || '';
          bodyInput.value = data.body || '';
        } else {
          subjectInput.value = '';
          bodyInput.value = 'Ошибка загрузки шаблона.';
        }
      } catch (error) {
        logAjaxError('load email preview', error, { url: previewUrlTemplate });
        subjectInput.value = '';
        bodyInput.value = 'Ошибка загрузки шаблона.';
      } finally {
        sendButton.removeAttribute('disabled');
      }
    }

    templateTypeSelect.addEventListener('change', fetchPreview);
    languageSelect.addEventListener('change', fetchPreview);

    modal.addEventListener('show.bs.modal', () => {
      if (templateTypeSelect.value !== 'custom' && !subjectInput.value) {
        fetchPreview();
      }
    });

    form.addEventListener('submit', () => {
      setTimeout(() => {
        sendButton.setAttribute('disabled', 'disabled');
        sendButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Отправка...';
      }, 0);
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    initPriceAutoFill();
    initAddPaymentForm();
    initEditPaymentModal();
    initPaymentDeletion();
    initDocumentUploadModal();
    initChecklistRefresher();
    initDocumentDeletion();
    initDocumentVerification();
    initBulkVerification();
    initHoverDropdowns();
    initSendEmailModal();
  });
})();

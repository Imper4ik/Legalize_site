(function () {
  let refreshChecklist = null;
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
        const url = template.replace('__service__', encodeURIComponent(service));
        const response = await fetch(url, {
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          credentials: 'same-origin',
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (Object.prototype.hasOwnProperty.call(data, 'price')) {
          const price = Number.parseFloat(data.price);
          priceInput.value = Number.isFinite(price) ? price.toFixed(2) : '0.00';
        }
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Не удалось получить цену услуги:', error);
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
    newItem.innerHTML = html.trim();

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
      existing.innerHTML = html.trim();
    }
  }

  function getErrorMessage(errors) {
    if (!errors) {
      return 'Не удалось сохранить платёж. Попробуйте ещё раз.';
    }

    if (typeof errors === 'string') {
      return errors;
    }

    const firstField = Object.values(errors)[0];
    if (Array.isArray(firstField) && firstField.length > 0) {
      return firstField[0];
    }

    return 'Не удалось сохранить платёж. Попробуйте ещё раз.';
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
        const response = await fetch(form.action, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          body: new FormData(form),
        });

        const data = await response.json();
        if (data.status === 'success' && data.html) {
          prependPaymentItem(data.html, data.payment_id);
          bootstrap.Modal.getOrCreateInstance(modal).hide();
          form.reset();
          showPaymentAlert('Платёж успешно добавлен.');
          return;
        }

        showPaymentAlert(getErrorMessage(data.errors || data.message), 'danger');
      } catch (error) {
        console.error('Ошибка при создании платежа', error);
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
    modal.addEventListener('show.bs.modal', (event) => {
      const button = event.relatedTarget;
      if (!button) {
        return;
      }
      const action = button.getAttribute('data-form-action');
      if (!action) {
        return;
      }
      const form = modal.querySelector('#editPaymentForm');
      if (form) {
        form.setAttribute('action', action);
      }
    });

    const form = modal.querySelector('#editPaymentForm');
    if (!form) {
      return;
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submitButton = form.querySelector('[type="submit"]');
      submitButton?.setAttribute('disabled', 'disabled');

      try {
        const response = await fetch(form.action, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          body: new FormData(form),
        });

        const data = await response.json();
        if (data.status === 'success' && data.html && data.payment_id) {
          updatePaymentItem(data.html, data.payment_id);
          bootstrap.Modal.getOrCreateInstance(modal).hide();
          showPaymentAlert('Платёж успешно обновлён.');
          return;
        }

        showPaymentAlert(getErrorMessage(data.errors || data.message), 'danger');
      } catch (error) {
        console.error('Ошибка при обновлении платежа', error);
        showPaymentAlert('Не удалось обновить платёж. Попробуйте ещё раз.', 'danger');
      } finally {
        submitButton?.removeAttribute('disabled');
        parseButton?.removeAttribute('disabled');
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
    const csrfToken = form.querySelector('[name="csrfmiddlewaretoken"]')?.value || '';

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

      try {
        const response = await fetch(form.action, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          body: new FormData(form),
          credentials: 'same-origin',
        });

        const data = await response.json();
        if (data.status === 'success') {
          if (data.pending_confirmation && confirmStep && confirmActions && uploadActions) {
            const parsed = data.parsed || {};
            if (parsedFirstName) parsedFirstName.value = parsed.first_name || '';
            if (parsedLastName) parsedLastName.value = parsed.last_name || '';
            if (parsedCaseNumber) parsedCaseNumber.value = parsed.case_number || '';
            if (parsedFingerprintsDate) parsedFingerprintsDate.value = parsed.fingerprints_date || '';
            if (parsedFingerprintsTime) parsedFingerprintsTime.value = parsed.fingerprints_time || '';
            if (parsedFingerprintsLocation) parsedFingerprintsLocation.value = parsed.fingerprints_location || '';
            if (parsedDecisionDate) parsedDecisionDate.value = parsed.decision_date || '';

            // Handle Raw Text Debugging
            const rawTextarea = modal.querySelector('#wezwanieRawText');
            const rawTextContainer = modal.querySelector('#wezwanieRawTextContainer');
            const toggleRawBtn = modal.querySelector('#wezwanieToggleRawText');

            if (rawTextarea) {
              rawTextarea.value = parsed.raw_text || '';
            }
            if (rawTextContainer) {
              rawTextContainer.classList.add('d-none');
            }

            // Re-bind toggle button
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
            await refreshChecklist();
          } else {
            window.location.reload();
          }
          return;
        }

        showDocumentAlert(getErrorMessage(data.errors || data.message), 'danger');
      } catch (error) {
        console.error('Ошибка при загрузке документа:', error);
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

      const payload = new FormData();
      payload.append('first_name', parsedFirstName?.value || '');
      payload.append('last_name', parsedLastName?.value || '');
      payload.append('case_number', parsedCaseNumber?.value || '');
      payload.append('fingerprints_date', parsedFingerprintsDate?.value || '');
      payload.append('decision_date', parsedDecisionDate?.value || '');

      try {
        const response = await fetch(confirmUrl, {
          method: 'POST',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': csrfToken,
          },
          body: payload,
          credentials: 'same-origin',
        });

        const data = await response.json();
        if (data.status === 'success') {
          bootstrap.Modal.getOrCreateInstance(modal).hide();
          showDocumentAlert(data.message || 'Данные wezwanie подтверждены.');
          if (typeof refreshChecklist === 'function') {
            await refreshChecklist();
          } else {
            window.location.reload();
          }
          return;
        }

        showDocumentAlert(getErrorMessage(data.errors || data.message), 'danger');
      } catch (error) {
        console.error('Не удалось подтвердить wezwanie:', error);
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

    async function refresh() {
      const hasOpenModal = Boolean(document.querySelector('.modal.show'));
      if (isFetching || document.visibilityState !== 'visible' || hasOpenModal) {
        return;
      }

      const expanded = Array.from(accordion.querySelectorAll('.accordion-collapse.show')).map((panel) => panel.id);

      if (controller) {
        controller.abort();
      }
      controller = new AbortController();
      isFetching = true;

      try {
        const response = await fetch(refreshUrl, {
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          credentials: 'same-origin',
          cache: 'no-store',
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const html = await response.text();
        const wrapper = document.createElement('div');
        wrapper.innerHTML = html.trim();
        accordion.innerHTML = wrapper.innerHTML;
        restoreExpandedPanels(expanded);
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Ошибка при обновлении чеклиста клиента:', error);
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
      // Restart the refresher only when all modals are closed
      if (!document.querySelector('.modal.show')) {
        startInterval();
      }
    });

    document.addEventListener('visibilitychange', refresh);
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

      try {
        const response = await fetch(form.action, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          body: new FormData(form),
          credentials: 'same-origin',
        });

        const data = await response.json();
        if (data.status === 'success') {
          if (typeof refreshChecklist === 'function') {
            await refreshChecklist();
          } else {
            window.location.reload();
          }
        }
      } catch (error) {
        console.error('Не удалось удалить документ из чеклиста:', error);
      } finally {
        button.removeAttribute('disabled');
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

      try {
        const response = await fetch(form.action, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          body: new FormData(form),
          credentials: 'same-origin',
        });

        const data = await response.json();
        if (data.status === 'success') {
          showDocumentAlert('Все загруженные документы отмечены как проверенные.');
          if (typeof refreshChecklist === 'function') {
            await refreshChecklist();
          } else {
            window.location.reload();
          }
          return;
        }

        showDocumentAlert(getErrorMessage(data.errors || data.message), 'danger');
      } catch (error) {
        console.error('Не удалось отметить все документы как проверенные:', error);
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
    if (!modal) return;

    const previewUrlTemplate = modal.dataset.previewUrl;
    const templateTypeSelect = modal.querySelector('#emailTemplateType');
    const languageSelect = modal.querySelector('#emailLanguage');
    const subjectInput = modal.querySelector('#emailSubject');
    const bodyInput = modal.querySelector('#emailBody');
    const sendButton = modal.querySelector('#sendEmailButton');
    const form = modal.querySelector('#sendEmailForm');

    if (!previewUrlTemplate || !templateTypeSelect || !languageSelect || !subjectInput || !bodyInput) return;

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

        const response = await fetch(url, {
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });

        if (response.ok) {
          const data = await response.json();
          subjectInput.value = data.subject || '';
          bodyInput.value = data.body || '';
        } else {
          console.error("Ошибка загрузки шаблона", response.status);
          subjectInput.value = '';
          bodyInput.value = 'Ошибка загрузки шаблона.';
        }
      } catch (error) {
        console.error("Ошибка сети при загрузке шаблона", error);
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
      sendButton.setAttribute('disabled', 'disabled');
      sendButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Отправка...';
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    initPriceAutoFill();
    initAddPaymentForm();
    initEditPaymentModal();
    initDocumentUploadModal();
    initChecklistRefresher();
    initDocumentDeletion();
    initBulkVerification();
    initHoverDropdowns();
    initSendEmailModal();
  });
})();

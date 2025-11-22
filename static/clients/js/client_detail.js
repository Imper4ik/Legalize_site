(function () {
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

  function showPaymentAlert(message, type = 'success') {
    const container = document.getElementById('payment-alerts');
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
    });

    modal.addEventListener('hidden.bs.modal', () => {
      if (form) {
        form.reset();
      }
      if (description) {
        description.textContent = '';
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
      if (isFetching || document.visibilityState !== 'visible' || document.body.classList.contains('modal-open')) {
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

    const intervalId = window.setInterval(refresh, 8000);
    document.addEventListener('visibilitychange', refresh);
    window.addEventListener('beforeunload', () => {
      window.clearInterval(intervalId);
      if (controller) {
        controller.abort();
      }
    });

    refresh();
  }

  document.addEventListener('DOMContentLoaded', () => {
    initPriceAutoFill();
    initAddPaymentForm();
    initEditPaymentModal();
    initDocumentUploadModal();
    initChecklistRefresher();
  });
})();

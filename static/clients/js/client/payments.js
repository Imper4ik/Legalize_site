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
    emptyState.textContent = list.dataset.emptyText || 'No payment invoices created yet.';
    list.append(emptyState);
  }
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
    const list = document.getElementById('payment-list-container');

    try {
      const { response, data } = await fetchJson(form.action, {
        method: 'POST',
        body: new FormData(form),
      });

      if (response.ok && data.status === 'success' && data.html) {
        prependPaymentItem(data.html, data.payment_id);
        bootstrap.Modal.getOrCreateInstance(modal).hide();
        form.reset();
        showPaymentAlert(list?.dataset.paymentCreated || 'Payment added successfully.');
        return;
      }

      showPaymentAlert(
        getErrorMessage(data.errors || data.message, list?.dataset.paymentCreateError || 'Failed to create payment. Please try again.'),
        'danger',
      );
    } catch (error) {
      logAjaxError('create payment', error, { url: form.action });
      showPaymentAlert(list?.dataset.paymentCreateError || 'Failed to create payment. Please try again.', 'danger');
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
    const list = document.getElementById('payment-list-container');

    try {
      const { response, data } = await fetchJson(form.action, {
        method: 'POST',
        body: new FormData(form),
      });

      if (response.ok && data.status === 'success' && data.html && data.payment_id) {
        updatePaymentItem(data.html, data.payment_id);
        bootstrap.Modal.getOrCreateInstance(modal).hide();
        showPaymentAlert(list?.dataset.paymentUpdated || 'Payment updated successfully.');
        return;
      }

      showPaymentAlert(
        getErrorMessage(data.errors || data.message, list?.dataset.paymentUpdateError || 'Failed to update payment. Please try again.'),
        'danger',
      );
    } catch (error) {
      logAjaxError('edit payment', error, { url: form.action });
      showPaymentAlert(list?.dataset.paymentUpdateError || 'Failed to update payment. Please try again.', 'danger');
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
        showPaymentAlert(data.message || list.dataset.paymentDeleted || 'Payment deleted successfully.');
        return;
      }

      showPaymentAlert(
        getErrorMessage(data.errors || data.message, list.dataset.paymentDeleteError || 'Failed to delete payment. Please try again.'),
        'danger',
      );
    } catch (error) {
      logAjaxError('delete payment', error, { url: form.action, paymentId });
      showPaymentAlert(list.dataset.paymentDeleteError || 'Failed to delete payment. Please try again.', 'danger');
    } finally {
      button.removeAttribute('disabled');
    }
  });
}

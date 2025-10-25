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
    initEditPaymentModal();
    initChecklistRefresher();
  });
})();

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
  initEmailHistoryToggle();
  initTabAnchorLinks();
  initOnboardingPanelLinkGenerator();
});

function initTabAnchorLinks() {
  document.body.addEventListener('click', (e) => {
    const link = e.target.closest('a[href^="#"]');
    if (!link) return;

    const targetId = link.getAttribute('href');
    if (targetId === '#') return;

    const targetElement = document.querySelector(targetId);
    if (!targetElement) return;

    const tabPane = targetElement.closest('.tab-pane');
    if (tabPane) {
      const tabId = tabPane.getAttribute('id');
      const tabTrigger = document.querySelector(`button[data-bs-target="#${tabId}"], a[data-bs-target="#${tabId}"]`);
      if (tabTrigger && !tabPane.classList.contains('active')) {
        e.preventDefault();
        const tab = bootstrap.Tab.getOrCreateInstance(tabTrigger);
        tab.show();

        setTimeout(() => {
          targetElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 150);
      }
    }
  });
}

function initOnboardingPanelLinkGenerator() {
  const btn = document.getElementById('btn-generate-detail-onboarding');
  if (!btn) return;

  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    const url = btn.dataset.generateUrl;
    if (!url) return;

    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = 'Генерация...';

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || 
                      document.querySelector('[name=csrfmiddlewaretoken]')?.value;

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'application/json',
          'X-CSRFToken': csrfToken,
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      if (data.status === 'ok') {
        const linkInput = document.getElementById('onboardingLink');
        const copyBtn = document.getElementById('btn-copy-onboarding-link');
        const infoEl = document.getElementById('onboarding-session-info');

        if (linkInput) {
          linkInput.value = data.link;
        }
        if (copyBtn) {
          copyBtn.disabled = false;
        }
        if (infoEl) {
          // Update status message with +7 days from now
          const now = new Date();
          now.setDate(now.getDate() + 7);
          const day = String(now.getDate()).padStart(2, '0');
          const month = String(now.getMonth() + 1).padStart(2, '0');
          const year = now.getFullYear();
          const hour = String(now.getHours()).padStart(2, '0');
          const minute = String(now.getMinutes()).padStart(2, '0');
          
          let statusText = 'Создана';
          const lang = document.documentElement.lang || 'en';
          if (lang.startsWith('ru')) {
            infoEl.innerHTML = `Текущая сессия: <strong>Создана</strong> (истекает: ${day}.${month}.${year} ${hour}:${minute})`;
          } else if (lang.startsWith('pl')) {
            infoEl.innerHTML = `Bieżąca sesja: <strong>Utworzona</strong> (wygasa: ${day}.${month}.${year} ${hour}:${minute})`;
          } else {
            infoEl.innerHTML = `Current session: <strong>Created</strong> (expires: ${day}.${month}.${year} ${hour}:${minute})`;
          }
        }

        // Copy to clipboard
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(data.link);
        }

        // Show alert
        showAlert('onboarding-alerts', data.message || 'Ссылка скопирована в буфер обмена!', 'success');
      } else {
        throw new Error(data.message || 'Ошибка генерации');
      }
    } catch (error) {
      console.error(error);
      showAlert('onboarding-alerts', 'Не удалось сгенерировать ссылку. Попробуйте еще раз.', 'danger');
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });
}


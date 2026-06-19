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
  const purposeSelect = document.getElementById('detail-onboarding-purpose');

  btn.addEventListener('click', async (e) => {
    e.preventDefault();
    const url = btn.dataset.generateUrl;
    if (!url) return;

    const lang = document.documentElement.lang || 'en';
    btn.disabled = true;
    const originalText = btn.textContent;
    
    let genText = btn.dataset.textGeneratingEn || 'Generating...';
    if (lang.startsWith('ru')) {
      genText = btn.dataset.textGeneratingRu || genText;
    } else if (lang.startsWith('pl')) {
      genText = btn.dataset.textGeneratingPl || genText;
    }
    btn.textContent = genText;

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || 
                      document.querySelector('[name=csrfmiddlewaretoken]')?.value;

    const intakeTypeSelect = document.getElementById('detail-onboarding-intake-type');

    try {
      const formData = new FormData();
      if (purposeSelect && purposeSelect.value) {
        formData.append('application_purpose', purposeSelect.value);
      }
      if (intakeTypeSelect && intakeTypeSelect.value) {
        formData.append('intake_type', intakeTypeSelect.value);
      }
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: formData,
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
          const formattedDate = `${day}.${month}.${year} ${hour}:${minute}`;
          
          let template = infoEl.dataset.labelEn || 'Current session: <strong>Created</strong> (expires: {date})';
          if (lang.startsWith('ru')) {
            template = infoEl.dataset.labelRu || template;
          } else if (lang.startsWith('pl')) {
            template = infoEl.dataset.labelPl || template;
          }
          infoEl.innerHTML = template.replace('{date}', formattedDate);
        }

        // Copy to clipboard
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(data.link);
        }

        // Show alert
        showAlert('onboarding-alerts', data.message || 'Link copied to clipboard!', 'success');
      } else {
        throw new Error(data.message || 'Generation error');
      }
    } catch (error) {
      console.error(error);
      let errorMsg = btn.dataset.errorEn || 'Failed to generate link. Please try again.';
      if (lang.startsWith('ru')) {
        errorMsg = btn.dataset.errorRu || errorMsg;
      } else if (lang.startsWith('pl')) {
        errorMsg = btn.dataset.errorPl || errorMsg;
      }
      showAlert('onboarding-alerts', errorMsg, 'danger');
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });
}


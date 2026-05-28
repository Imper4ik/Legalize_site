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


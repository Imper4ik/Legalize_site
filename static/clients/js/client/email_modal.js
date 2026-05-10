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

    subjectInput.value = modal.dataset.loadingText || 'Loading...';
    bodyInput.value = modal.dataset.loadingTemplateText || 'Loading template...';
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
        bodyInput.value = modal.dataset.errorLoadingTemplate || 'Error loading template.';
      }
    } catch (error) {
      logAjaxError('load email preview', error, { url: previewUrlTemplate });
      subjectInput.value = '';
      bodyInput.value = modal.dataset.errorLoadingTemplate || 'Error loading template.';
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
      const sendingText = modal.dataset.sendingText || 'Sending...';
      sendButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${sendingText}`;
    }, 0);
  });
}

function initEmailHistoryToggle() {
  document.addEventListener('click', (event) => {
    const toggleBtn = event.target.closest('.email-history-toggle');
    if (!toggleBtn) return;

    const container = toggleBtn.closest('.card');
    if (!container) return;

    const extraRows = container.querySelectorAll('.email-log-extra');
    const isHidden = extraRows[0]?.classList.contains('d-none');

    const showMoreLabel = toggleBtn.dataset.labelShowMore || 'Show more';
    const showLessLabel = toggleBtn.dataset.labelShowLess || 'Collapse';
    const hiddenCount = toggleBtn.dataset.hiddenCount || '0';

    extraRows.forEach((row) => {
      if (isHidden) {
        row.classList.remove('d-none');
      } else {
        row.classList.add('d-none');
      }
    });

    if (isHidden) {
      toggleBtn.textContent = showLessLabel;
    } else {
      toggleBtn.textContent = `${showMoreLabel} ${hiddenCount}`;
    }
  });
}

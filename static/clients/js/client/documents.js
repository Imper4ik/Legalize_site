async function refreshAndScrollToChecklist(docType) {
  if (typeof refreshChecklist === 'function') {
    await refreshChecklist({ force: true });
    if (docType) {
      const targetHeader = document.getElementById('heading' + docType);
      if (targetHeader) {
        const collapseEl = document.getElementById('collapse' + docType);
        if (collapseEl) {
          const instance = bootstrap.Collapse.getOrCreateInstance(collapseEl, { toggle: false });
          instance.show();
        }
        setTimeout(() => {
          targetHeader.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 200);
      }
    }
  } else {
    if (docType) {
      window.location.hash = 'heading' + docType;
    }
    window.location.reload();
  }
}

function initDocumentUploadModal() {
  const modal = document.getElementById('uploadDocumentModal');
  if (!modal) {
    return;
  }

  const description = modal.querySelector('#uploadDocumentDescription');
  const form = modal.querySelector('form');
  let currentDocType = '';
  const actionTemplate = modal.dataset.actionTemplate;
  const confirmTemplate = modal.dataset.confirmUrlTemplate;
  const parseInput = modal.querySelector('#uploadDocumentParseWezwanie');
  const parsedDataUrlTemplate = modal.dataset.parsedDataUrlTemplate;
  const confirmStep = modal.querySelector('#wezwanieConfirmationStep');
  const confirmActions = modal.querySelector('#wezwanieConfirmActions');
  const uploadActions = modal.querySelector('#uploadDocumentActions');
  const uploadStep = modal.querySelector('#uploadDocumentStep');
  const confirmButton = modal.querySelector('#wezwanieConfirmButton');
  const parsedFirstName = modal.querySelector('#wezwanieParsedFirstName');
  const parsedLastName = modal.querySelector('#wezwanieParsedLastName');
  const parsedCaseNumber = modal.querySelector('#wezwanieParsedCaseNumber');
  const parsedFingerprintsDate = modal.querySelector('#wezwanieParsedFingerprintsDate');
  const parsedFingerprintsTime = modal.querySelector('#wezwanieParsedFingerprintsTime');
  const parsedFingerprintsLocation = modal.querySelector('#wezwanieParsedFingerprintsLocation');
  const parsedTicketNumber = modal.querySelector('#wezwanieParsedTicketNumber');
  const parsedListName = modal.querySelector('#wezwanieParsedListName');
  const parsedStatusCode = modal.querySelector('#wezwanieParsedStatusCode');
  const parsedDecisionDate = modal.querySelector('#wezwanieParsedDecisionDate');

  if (!form) {
    return;
  }

  const submitButton = form.querySelector('#uploadDocumentSubmitButton');
  const parseButton = form.querySelector('#wezwanieParseButton');

  function fillWezwanieParsedFields(parsed = {}) {
    if (parsedFirstName) parsedFirstName.value = parsed.first_name || '';
    if (parsedLastName) parsedLastName.value = parsed.last_name || '';
    if (parsedCaseNumber) parsedCaseNumber.value = parsed.case_number || '';
    if (parsedFingerprintsDate) parsedFingerprintsDate.value = parsed.fingerprints_date || '';
    if (parsedFingerprintsTime) parsedFingerprintsTime.value = parsed.fingerprints_time || '';
    if (parsedFingerprintsLocation) parsedFingerprintsLocation.value = parsed.fingerprints_location || '';
    if (parsedTicketNumber) parsedTicketNumber.value = parsed.ticket_number || '';
    if (parsedListName) parsedListName.value = parsed.list_name || '';
    if (parsedStatusCode) parsedStatusCode.value = parsed.application_status_code || '';
    if (parsedDecisionDate) parsedDecisionDate.value = parsed.decision_date || '';
  }

  function buildDocumentUrl(template, docId, fallbackPath) {
    const encodedDocId = encodeURIComponent(docId);
    if (!template) {
      return fallbackPath(encodedDocId);
    }
    if (template.includes('__doc_id__')) {
      return template.replace('__doc_id__', encodedDocId);
    }
    return template.replace('/0/', `/${encodedDocId}/`);
  }

  function resetConfirmation() {
    uploadStep?.classList.remove('d-none');
    confirmStep?.classList.add('d-none');
    confirmActions?.classList.add('d-none');
    uploadActions?.classList.remove('d-none');
    if (parseInput) {
      parseInput.value = '0';
    }
    fillWezwanieParsedFields();
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
    const defaultZusPeriodMonth = button.getAttribute('data-zus-period-month') || '';

    if (docType) {
      currentDocType = docType;
      form.setAttribute('action', actionTemplate.replace('__doc_type__', encodeURIComponent(docType)));
    }

    if (description) {
      const uploadPrefix = modal.dataset.uploadingDocumentPrefix || 'You are uploading document:';
      description.textContent = docName ? `${uploadPrefix} "${docName}"` : '';
    }

    const WEZWANIE_DOCUMENT_TYPES = [
      'wezwanie',
      'fingerprint_confirmation',
      'formal_deficiencies',
      'formal_deficiencies_wezwanie',
      'braki_formalne',
      'braki_formalne_wezwanie',
    ];

    function isWezwanieDocumentType(code) {
      return code && WEZWANIE_DOCUMENT_TYPES.includes(code.toLowerCase());
    }

    const isWezwanie = isWezwanieDocumentType(docType);
    if (parseButton && submitButton) {
      if (isWezwanie) {
        parseButton.classList.remove('d-none');
        submitButton.classList.remove('d-none');
        submitButton.innerHTML = modal.dataset.uploadOnlyText || 'Just upload';
      } else {
        parseButton.classList.add('d-none');
        submitButton.classList.remove('d-none');
        submitButton.innerHTML = modal.dataset.uploadText || 'Upload';
      }
    }

    const isZusRca = docType === 'zus_rca_or_insurance';
    const zusGroup = modal.querySelector('#zusPeriodMonthGroup');
    const zusInput = modal.querySelector('#id_zus_period_month');
    const fileInput = modal.querySelector('#id_file');
    if (zusGroup) zusGroup.classList.toggle('d-none', !isZusRca);
    if (zusInput) {
      zusInput.required = false;
      zusInput.value = isZusRca ? defaultZusPeriodMonth : '';
    }
    if (fileInput) {
      if (isZusRca) {
        fileInput.removeAttribute('multiple');
      } else {
        fileInput.setAttribute('multiple', 'multiple');
      }
    }

    resetConfirmation();
  });

  modal.addEventListener('hidden.bs.modal', () => {
    form.reset();
    if (description) {
      description.textContent = '';
    }
    const zusGroup = modal.querySelector('#zusPeriodMonthGroup');
    const zusInput = modal.querySelector('#id_zus_period_month');
    const fileInput = modal.querySelector('#id_file');
    if (zusGroup) zusGroup.classList.add('d-none');
    if (zusInput) {
      zusInput.required = false;
      zusInput.value = '';
    }
    if (fileInput) fileInput.setAttribute('multiple', 'multiple');
    resetConfirmation();
  });

  submitButton?.addEventListener('click', () => {
    if (parseInput) parseInput.value = '0';
  });

  parseButton?.addEventListener('click', () => {
    if (parseInput) parseInput.value = '1';
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    
    const isParsing = parseInput && parseInput.value === '1';
    const originalSubmitText = submitButton?.innerHTML;
    const originalParseText = parseButton?.innerHTML;

    if (submitButton) {
      submitButton.setAttribute('disabled', 'disabled');
    }
    if (parseButton) {
      parseButton.setAttribute('disabled', 'disabled');
      if (isParsing) {
        const text = modal.dataset.recognizingText || 'Recognizing document...';
        parseButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${text}`;
      }
    }
    
    pauseChecklistRefresh();

    try {
      const { response, data } = await fetchJson(form.action, {
        method: 'POST',
        body: new FormData(form),
      });

      if (response.ok && data.status === 'success') {
        // ... (existing success logic)
        if (data.pending_confirmation && confirmStep && confirmActions && uploadActions) {
          const parsed = data.parsed || {};
          fillWezwanieParsedFields(parsed);

          confirmStep.classList.remove('d-none');
          confirmActions.classList.remove('d-none');
          uploadActions.classList.add('d-none');

          if (confirmButton) {
            const confirmUrl = data.confirm_url || buildDocumentUrl(
              confirmTemplate,
              data.doc_id,
              (encodedDocId) => `/staff/document/${encodedDocId}/confirm-wezwanie/`,
            );
            confirmButton.dataset.confirmUrl = confirmUrl;
          }
          return;
        }

        bootstrap.Modal.getOrCreateInstance(modal).hide();
        showDocumentAlert(data.message || modal.dataset.uploadSuccessText || 'Document uploaded successfully.');
        await refreshAndScrollToChecklist(currentDocType);
        return;
      }

      console.error('Document upload error:', { status: response.status, data });
      showDocumentAlert(
        getErrorMessage(data.errors || data.message, modal.dataset.uploadErrorText || 'Failed to upload document. Please try again.'),
        'danger',
      );
    } catch (error) {
      logAjaxError('upload document', error, { url: form.action });
      console.error('AJAX Catch - upload document:', error);
      
      let errMsg = error.message || modal.dataset.uploadErrorText || 'Failed to upload document. Please try again.';
      if (error.responseStatus === 413) {
        errMsg = modal.dataset.fileTooLargeText || 'File too large.';
      } else if (error.responseText && error.responseText.includes('CSRF')) {
        errMsg = modal.dataset.sessionExpiredText || 'Session expired. Please refresh the page.';
      }
      showDocumentAlert(errMsg, 'danger');
    } finally {
      if (submitButton) {
        submitButton.removeAttribute('disabled');
        if (originalSubmitText) submitButton.innerHTML = originalSubmitText;
      }
      if (parseButton) {
        parseButton.removeAttribute('disabled');
        if (originalParseText) parseButton.innerHTML = originalParseText;
      }
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
    payload.append('fingerprints_time', parsedFingerprintsTime?.value || '');
    payload.append('fingerprints_location', parsedFingerprintsLocation?.value || '');
    payload.append('ticket_number', modal.querySelector('#wezwanieParsedTicketNumber')?.value || '');
    payload.append('list_name', modal.querySelector('#wezwanieParsedListName')?.value || '');
    payload.append('application_status_code', modal.querySelector('#wezwanieParsedStatusCode')?.value || '');
    payload.append('decision_date', parsedDecisionDate?.value || '');

    try {
      const { response, data } = await fetchJson(confirmUrl, {
        method: 'POST',
        body: payload,
      });

      if (response.ok && data.status === 'success') {
        bootstrap.Modal.getOrCreateInstance(modal).hide();
        showDocumentAlert(data.message || modal.dataset.wezwanieConfirmed || 'Wezwanie data confirmed.');
        await refreshAndScrollToChecklist(currentDocType);
        return;
      }

      showDocumentAlert(
        getErrorMessage(data.errors || data.message, modal.dataset.wezwanieConfirmError || 'Failed to confirm wezwanie data.'),
        'danger',
      );
    } catch (error) {
      logAjaxError('confirm wezwanie', error, { url: confirmUrl });
      showDocumentAlert(modal.dataset.wezwanieConfirmError || 'Failed to confirm wezwanie data.', 'danger');
    } finally {
      confirmButton.removeAttribute('disabled');
    }
  });

  // Handle "Review OCR Data" button clicks
  document.addEventListener('click', async (event) => {
    const reviewBtn = event.target.closest('.review-ocr-data-btn');
    if (!reviewBtn) return;
    
    const docId = reviewBtn.dataset.docId;
    if (!docId) return;

    const docType = reviewBtn.dataset.docType;

    // Show a loading state if needed
    reviewBtn.setAttribute('disabled', 'disabled');
    const originalText = reviewBtn.innerHTML;
    reviewBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';

    try {
      const url = buildDocumentUrl(
        parsedDataUrlTemplate,
        docId,
        (encodedDocId) => `/staff/document/${encodedDocId}/parsed-data/`,
      );
      const { response, data } = await fetchJson(url);
      if (response.ok && data.parsed_data) {
        const parsed = data.parsed_data;

        fillWezwanieParsedFields(parsed);

        if (uploadStep) uploadStep.classList.add('d-none');
        
        confirmStep.classList.remove('d-none');
        confirmActions.classList.remove('d-none');
        uploadActions.classList.add('d-none');

        if (confirmButton) {
          const confirmUrl = buildDocumentUrl(
            confirmTemplate,
            docId,
            (encodedDocId) => `/staff/document/${encodedDocId}/confirm-wezwanie/`,
          );
          confirmButton.dataset.confirmUrl = confirmUrl;
        }

        if (description) {
          description.textContent = modal.dataset.ocrCheckData || 'Check data extracted from document:';
        }

        bootstrap.Modal.getOrCreateInstance(modal).show();
      } else {
        showDocumentAlert(modal.dataset.ocrLoadError || 'Failed to load OCR data.', 'danger');
      }
    } catch (error) {
      logAjaxError('review OCR data', error);
      showDocumentAlert(modal.dataset.ocrLoadError || 'Failed to load OCR data.', 'danger');
    } finally {
      reviewBtn.removeAttribute('disabled');
      reviewBtn.innerHTML = originalText;
    }
  });
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
    const modal = document.getElementById('uploadDocumentModal');

    const accordionItem = button.closest('.accordion-item');
    let docType = '';
    if (accordionItem) {
      const header = accordionItem.querySelector('.accordion-header');
      if (header && header.id) {
        docType = header.id.replace('heading', '');
      }
    }

    try {
      const { response, data } = await fetchJson(form.action, {
        method: 'POST',
        body: new FormData(form),
      });

      if (response.ok && data.status === 'success') {
        showDocumentAlert(data.message || modal?.dataset.documentDeleted || 'Document deleted.');
        await refreshAndScrollToChecklist(docType);
        return;
      }

      showDocumentAlert(
        getErrorMessage(data.errors || data.message, modal?.dataset.documentDeleteError || 'Failed to delete document. Please try again.'),
        'danger',
      );
    } catch (error) {
      logAjaxError('delete document', error, { url: form.action });
      showDocumentAlert(modal?.dataset.documentDeleteError || 'Failed to delete document. Please try again.', 'danger');
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
    const modal = document.getElementById('uploadDocumentModal');

    const accordionItem = form.closest('.accordion-item');
    let docType = '';
    if (accordionItem) {
      const header = accordionItem.querySelector('.accordion-header');
      if (header && header.id) {
        docType = header.id.replace('heading', '');
      }
    }

    try {
      const { response, data } = await fetchJson(form.action, {
        method: 'POST',
        body: new FormData(form),
      });

      if (response.ok && data.status === 'success') {
        const successMessage = data.emails_sent
          ? (modal?.dataset.statusUpdatedEmailSent || 'Document status updated. Email with missing documents sent.')
          : (modal?.dataset.statusUpdated || 'Document status updated.');
        showDocumentAlert(data.message || successMessage);
        await refreshAndScrollToChecklist(docType);
        return;
      }

      showDocumentAlert(
        getErrorMessage(data.errors || data.message, modal?.dataset.statusUpdateError || 'Failed to update document status. Please try again.'),
        'danger',
      );
    } catch (error) {
      logAjaxError('toggle document verification', error, { url: form.action });
      showDocumentAlert(modal?.dataset.statusUpdateError || 'Failed to update document status. Please try again.', 'danger');
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

    const confirmText = form.dataset.confirmText;
    if (confirmText && !window.confirm(confirmText)) {
      return;
    }

    const submitButton = form.querySelector('[type="submit"]');
    submitButton?.setAttribute('disabled', 'disabled');
    pauseChecklistRefresh();

    try {
      const { response, data } = await fetchJson(form.action, {
        method: 'POST',
        body: new FormData(form),
      });

      if (response.ok && data.status === 'success') {
        if (data.message) {
          showDocumentAlert(data.message, data.verified_count > 0 ? 'success' : 'info');
        } else if (data.verified_count > 0) {
          const prefix = form.dataset.verifiedCountText || 'Documents marked:';
          showDocumentAlert(`${prefix} ${data.verified_count}.`);
        } else {
          showDocumentAlert(form.dataset.allVerifiedText || 'All documents have already been verified.', 'info');
        }
        if (typeof refreshChecklist === 'function') {
          await refreshChecklist({ force: true });
        } else {
          window.location.reload();
        }
        return;
      }

      showDocumentAlert(
        getErrorMessage(data.errors || data.message, form.dataset.updateErrorText || 'Failed to update document status. Please try again.'),
        'danger',
      );
    } catch (error) {
      logAjaxError('verify all documents', error, { url: form.action });
      showDocumentAlert(form.dataset.updateErrorText || 'Failed to update document status. Please try again.', 'danger');
    } finally {
      submitButton?.removeAttribute('disabled');
    }
  });
}

function initDocumentRejection() {
  const modal = document.getElementById('rejectDocumentModal');
  if (!modal) {
    return;
  }

  const form = modal.querySelector('#rejectDocumentForm');
  const reasonInput = modal.querySelector('#rejectDocumentReason');
  const submitBtn = modal.querySelector('#rejectDocumentSubmitBtn');
  let currentDocId = '';
  let rejectUrl = '';

  document.addEventListener('click', (event) => {
    const button = event.target.closest('.reject-document-btn');
    if (!button) {
      return;
    }
    currentDocId = button.getAttribute('data-doc-id');
    rejectUrl = button.getAttribute('data-reject-url');
    
    if (form && rejectUrl) {
      form.setAttribute('action', rejectUrl);
    }
    if (reasonInput) {
      reasonInput.value = '';
    }
  });

  if (!form) {
    return;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    if (submitBtn) {
      submitBtn.setAttribute('disabled', 'disabled');
    }
    pauseChecklistRefresh();

    try {
      const { response, data } = await fetchJson(form.action, {
        method: 'POST',
        body: new FormData(form),
      });

      if (response.ok && data.status === 'success') {
        bootstrap.Modal.getOrCreateInstance(modal).hide();
        showDocumentAlert(data.message || 'Document rejected.');
        
        let docType = '';
        const docRow = document.querySelector(`.reject-document-btn[data-doc-id="${currentDocId}"]`)?.closest('.accordion-item');
        if (docRow) {
          const header = docRow.querySelector('.accordion-header');
          if (header && header.id) {
            docType = header.id.replace('heading', '');
          }
        }
        await refreshAndScrollToChecklist(docType);
        return;
      }

      showDocumentAlert(
        getErrorMessage(data.errors || data.message, modal.dataset.rejectErrorText || 'Failed to reject document. Please try again.'),
        'danger',
      );
    } catch (error) {
      logAjaxError('reject document', error, { url: form.action });
      showDocumentAlert(modal.dataset.rejectErrorText || 'Failed to reject document. Please try again.', 'danger');
    } finally {
      if (submitBtn) {
        submitBtn.removeAttribute('disabled');
      }
    }
  });
}


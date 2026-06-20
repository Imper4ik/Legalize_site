function initMessageTemplatesModal() {
  const modal = document.getElementById('messageTemplatesModal');
  if (!modal) {
    return;
  }

  const templateType = modal.querySelector('#messageTemplateType');
  const templateLang = modal.querySelector('#messageTemplateLanguage');
  const docSelectGroup = modal.querySelector('#templateDocSelectGroup');
  const docSelect = modal.querySelector('#templateDocSelect');
  const reasonGroup = modal.querySelector('#templateRejectionReasonGroup');
  const reasonInput = modal.querySelector('#templateRejectionReason');
  const messageText = modal.querySelector('#generatedMessageText');
  const copyBtn = modal.querySelector('#btnCopyGeneratedMessage');

  const clientName = modal.dataset.clientFirstName || 'Client';

  // Read data markers from DOM checklist
  const labelAllRequired = modal.dataset.textAllRequired || 'All required documents';
  const missingDocs = Array.from(document.querySelectorAll('.missing-doc-item'))
    .map(el => el.dataset.name)
    .filter(Boolean)
    .join(', ') || labelAllRequired;

  const labelLastMonth = modal.dataset.textLastMonth || 'last month';
  const missingZus = Array.from(document.querySelectorAll('.missing-zus-month'))
    .map(el => el.dataset.value)
    .filter(Boolean)
    .join(', ') || labelLastMonth;

  function populateDocSelect() {
    if (!docSelect) return;
    docSelect.innerHTML = '';
    
    const items = document.querySelectorAll('.accordion-item');
    items.forEach(item => {
      const typeLabel = item.querySelector('.checklist-title')?.textContent.trim() || '';
      const rows = item.querySelectorAll('.checklist-document-row');
      rows.forEach(row => {
        const fileLabelEl = row.querySelector('.fw-semibold');
        const fileLabel = fileLabelEl ? fileLabelEl.textContent.trim() : 'File';
        const displayLabel = typeLabel ? `${typeLabel} (${fileLabel})` : fileLabel;
        
        const reasonEl = row.querySelector('.text-danger');
        let reason = '';
        if (reasonEl) {
          const strongEl = reasonEl.querySelector('strong');
          reason = reasonEl.textContent.trim();
          if (strongEl) {
            reason = reason.replace(strongEl.textContent.trim(), '').replace(':', '').trim();
          }
        }

        const opt = document.createElement('option');
        opt.value = typeLabel || fileLabel;
        opt.dataset.reason = reason;
        opt.textContent = displayLabel;
        docSelect.appendChild(opt);
      });
    });
  }

  function updateMessage() {
    const type = templateType.value;
    const lang = templateLang.value;
    
    const showDoc = (type === 'document_rejected' || type === 'document_accepted');
    docSelectGroup.classList.toggle('d-none', !showDoc);
    reasonGroup.classList.toggle('d-none', type !== 'document_rejected');

    // Read template from dataset
    const datasetKey = 'tpl' + type.replace(/_([a-z])/g, (g) => g[1].toUpperCase()) + lang.toUpperCase();
    let text = modal.dataset[datasetKey] || '';
    
    text = text.replace(/{name}/g, clientName);
    text = text.replace(/{docs}/g, missingDocs);
    text = text.replace(/{zus}/g, missingZus);

    if (showDoc && docSelect.options.length > 0) {
      const selectedOpt = docSelect.options[docSelect.selectedIndex] || docSelect.options[0];
      const docName = selectedOpt.value;
      text = text.replace(/{doc_name}/g, docName);

      if (type === 'document_rejected') {
        const labelDefaultReason = modal.dataset.textDefaultReason || 'Blurry photo / invalid format';
        const defaultReason = reasonInput.value.trim() || selectedOpt.dataset.reason || labelDefaultReason;
        text = text.replace(/{reason}/g, defaultReason);
      }
    } else {
      const placeholderDoc = modal.dataset.textSelectDocPlaceholder || '[document name]';
      const placeholderReason = modal.dataset.textReasonPlaceholder || '[reason]';
      text = text.replace(/{doc_name}/g, placeholderDoc);
      text = text.replace(/{reason}/g, placeholderReason);
    }

    messageText.value = text;
  }

  modal.addEventListener('show.bs.modal', () => {
    populateDocSelect();
    
    if (docSelect && docSelect.options.length > 0) {
      reasonInput.value = docSelect.options[0].dataset.reason || '';
    }

    updateMessage();
  });

  templateType.addEventListener('change', updateMessage);
  templateLang.addEventListener('change', updateMessage);
  
  if (docSelect) {
    docSelect.addEventListener('change', () => {
      const selectedOpt = docSelect.options[docSelect.selectedIndex];
      if (selectedOpt) {
        reasonInput.value = selectedOpt.dataset.reason || '';
      }
      updateMessage();
    });
  }
  
  reasonInput.addEventListener('input', updateMessage);

  copyBtn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(messageText.value);
      const originalText = copyBtn.innerHTML;
      const textCopied = modal.dataset.textCopied || 'Copied!';
      copyBtn.innerHTML = '<i class="bi bi-check2 me-1"></i>' + textCopied;
      setTimeout(() => {
        copyBtn.innerHTML = originalText;
      }, 2000);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  });
}

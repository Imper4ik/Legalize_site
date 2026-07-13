(function () {
  const PLACEHOLDER_TEXT = '—';

  function findAncestor(node, predicate) {
    let current = node;
    while (current && current !== document) {
      if (current.nodeType === Node.ELEMENT_NODE && predicate(current)) {
        return current;
      }
      current = current.parentNode;
    }
    return null;
  }

  function toggleBoldSelection() {
    const selection = window.getSelection();
    if (!selection.rangeCount || selection.isCollapsed) {
      return;
    }

    const range = selection.getRangeAt(0);
    const startStrong = findAncestor(range.startContainer, (node) => node.nodeName === 'STRONG');
    const endStrong = findAncestor(range.endContainer, (node) => node.nodeName === 'STRONG');

    if (startStrong && startStrong === endStrong) {
      const parent = startStrong.parentNode;
      if (!parent) {
        return;
      }
      const fragment = document.createDocumentFragment();
      while (startStrong.firstChild) {
        fragment.appendChild(startStrong.firstChild);
      }
      parent.replaceChild(fragment, startStrong);
      const newRange = document.createRange();
      newRange.selectNodeContents(parent);
      selection.removeAllRanges();
      selection.addRange(newRange);
      return;
    }

    const strong = document.createElement('strong');
    try {
      range.surroundContents(strong);
    } catch (error) {
      const fragment = range.extractContents();
      strong.appendChild(fragment);
      range.insertNode(strong);
    }
    const newRange = document.createRange();
    newRange.selectNodeContents(strong);
    selection.removeAllRanges();
    selection.addRange(newRange);
  }

  function selectionHasBold() {
    const selection = window.getSelection();
    if (!selection.rangeCount) {
      return false;
    }
    const anchor = selection.anchorNode;
    if (!anchor) {
      return false;
    }
    return Boolean(findAncestor(anchor, (node) => node.nodeName === 'STRONG'));
  }

  function enhanceEditors(root) {
    const editors = root.querySelectorAll('[data-notes-editor]');
    const forms = root.querySelectorAll('.notes-form');
    const boldIndicator = root.querySelector('[data-bold-indicator]');
    const boldButtons = root.querySelectorAll('[data-notes-bold]');

    function updateIndicator() {
      if (!boldIndicator) {
        return;
      }
      boldIndicator.style.display = selectionHasBold() ? 'inline-block' : 'none';
    }

    boldButtons.forEach((boldButton) => {
      // Bind on mousedown + preventDefault so clicking the button never moves
      // focus out of the contenteditable note and collapses the selection.
      // The previous click handler routinely lost the selection — the main
      // reason the single toolbar button felt unreliable.
      boldButton.addEventListener('mousedown', (event) => {
        event.preventDefault();
        toggleBoldSelection();
        updateIndicator();
      });
    });

    document.addEventListener('selectionchange', updateIndicator);

    editors.forEach((editor) => {
      const setPlaceholderState = () => {
        const text = (editor.textContent || '').trim();
        if (text.toLowerCase() === PLACEHOLDER_TEXT.toLowerCase()) {
          editor.classList.add('is-none');
        } else {
          editor.classList.remove('is-none');
        }
      };

      if ((editor.textContent || '').trim() === '') {
        editor.innerHTML = PLACEHOLDER_TEXT;
      }
      setPlaceholderState();

      editor.addEventListener('focus', () => {
        const text = (editor.textContent || '').trim();
        if (text.toLowerCase() === PLACEHOLDER_TEXT.toLowerCase()) {
          editor.textContent = '';
          editor.classList.remove('is-none');
        }
      });

      editor.addEventListener('blur', () => {
        const text = (editor.textContent || '').trim();
        if (text === '') {
          editor.textContent = PLACEHOLDER_TEXT;
          editor.classList.add('is-none');
        } else {
          setPlaceholderState();
        }
      });

      editor.addEventListener('keyup', updateIndicator);
      editor.addEventListener('mouseup', updateIndicator);

      // Bold the current selection in place with the standard Ctrl/Cmd+B
      // shortcut, so staff no longer have to reach for the single toolbar
      // button in the column header while editing a row far down the list.
      editor.addEventListener('keydown', (event) => {
        if ((event.ctrlKey || event.metaKey) && (event.key === 'b' || event.key === 'B')) {
          event.preventDefault();
          toggleBoldSelection();
          updateIndicator();
        }
      });
    });

    forms.forEach((form) => {
      form.addEventListener('submit', () => {
        const editor = form.querySelector('[data-notes-editor]');
        const hidden = form.querySelector('.hidden-notes-input');
        if (!editor || !hidden) {
          return;
        }
        const text = (editor.textContent || '').trim();
        if (text.toLowerCase() === PLACEHOLDER_TEXT.toLowerCase()) {
          hidden.value = '';
        } else {
          hidden.value = editor.innerHTML;
        }
      });
    });
  }

  async function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return await navigator.clipboard.writeText(text);
    }
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      document.execCommand('copy');
    } catch (err) {
      console.error('Fallback copy failed', err);
    }
    document.body.removeChild(textarea);
  }

  function parseGeneratedLinkResponse(data) {
    const payload = data && typeof data === 'object' ? data : {};
    const nested = payload.data && typeof payload.data === 'object' ? payload.data : {};
    const status = payload.status || nested.status || '';
    const message = payload.message || payload.error || nested.message || nested.error || 'Generation failed';
    const failed = (
      (status && status !== 'ok' && status !== 'success') ||
      payload.success === false ||
      payload.ok === false ||
      nested.success === false ||
      nested.ok === false
    );
    if (failed) {
      throw new Error(message);
    }

    const link = (
      payload.link ||
      payload.url ||
      payload.onboarding_url ||
      payload.onboardingUrl ||
      payload.portal_url ||
      payload.portalUrl ||
      nested.link ||
      nested.url ||
      nested.onboarding_url ||
      nested.onboardingUrl ||
      nested.portal_url ||
      nested.portalUrl ||
      ''
    );
    const succeeded = (
      status === 'ok' ||
      status === 'success' ||
      payload.success === true ||
      payload.ok === true ||
      nested.success === true ||
      nested.ok === true ||
      Boolean(link)
    );
    if (!succeeded || !link) {
      throw new Error(message);
    }

    return link;
  }
  let activeLink = '';
  let activeShareMode = 'onboarding';

  function openShareModal(link, mode = 'onboarding') {
    activeLink = link;
    activeShareMode = mode;
    const modalEl = document.getElementById('onboardingShareModal');
    if (!modalEl) return;

    // QR Code URL
    const qrImg = document.getElementById('share-qr-image');
    const qrSpinner = document.getElementById('share-qr-spinner');
    if (qrImg && qrSpinner) {
      qrImg.style.display = 'none';
      qrSpinner.style.display = 'block';

      qrImg.onload = null;
      qrImg.onerror = null;

      if (typeof QRious !== 'undefined') {
        try {
          const qr = new QRious({
            value: link,
            size: 150
          });
          qrImg.onload = () => {
            qrSpinner.style.display = 'none';
            qrImg.style.display = 'block';
          };
          qrImg.onerror = () => {
            qrSpinner.style.display = 'none';
            qrImg.style.display = 'block';
          };
          qrImg.src = qr.toDataURL();
        } catch (err) {
          console.error('Local QR generation failed', err);
          qrSpinner.style.display = 'none';
          qrImg.removeAttribute('src');
          qrImg.style.display = 'none';
        }
      } else {
        console.error('Local QR library is unavailable');
        qrSpinner.style.display = 'none';
        qrImg.removeAttribute('src');
        qrImg.style.display = 'none';
      }
    }

    // Default language is RU
    updateShareMessage('ru');

    // Make sure RU tab is active in the UI
    const ruTab = document.getElementById('share-lang-ru-tab');
    if (ruTab && window.bootstrap) {
      const tab = bootstrap.Tab.getOrCreateInstance(ruTab);
      tab.show();
    }

    if (window.bootstrap) {
      const shareModal = bootstrap.Modal.getOrCreateInstance(modalEl);
      shareModal.show();
    }
  }

  function updateShareMessage(lang) {
    const previewEl = document.getElementById('share-message-preview');
    if (!previewEl) return;

    let template = '';
    if (activeShareMode === 'intake') {
      if (lang === 'pl') {
        template = `Dzień dobry! Proszę kliknąć w link i wypełnić formularz wstępny, abyśmy mogli otworzyć sprawę: ${activeLink}`;
      } else if (lang === 'en') {
        template = `Hello! Please follow the link and complete the intake form so we can open your case: ${activeLink}`;
      } else {
        template = `Здравствуйте! Пожалуйста, перейдите по ссылке и заполните первичную анкету, чтобы мы могли открыть ваше дело: ${activeLink}`;
      }
    } else if (lang === 'pl') {
      template = `Dzień dobry! Proszę kliknąć w link, utworzyć hasło i przesłać dokumenty do sprawy: ${activeLink}`;
    } else if (lang === 'en') {
      template = `Hello! Please follow the link to set up your password and upload documents for your case: ${activeLink}`;
    } else {
      template = `Здравствуйте! Пожалуйста, перейдите по ссылке, создайте пароль и загрузите документы по вашему делу: ${activeLink}`;
    }

    previewEl.textContent = template;
  }

  function initShareModalListeners() {
    const modalEl = document.getElementById('onboardingShareModal');
    if (!modalEl) return;

    // Language pills
    const tabs = modalEl.querySelectorAll('#share-lang-tabs button[data-bs-toggle="pill"]');
    tabs.forEach((tab) => {
      tab.addEventListener('shown.bs.tab', (e) => {
        const lang = e.target.dataset.lang;
        updateShareMessage(lang);
      });
    });

    // Copy Message Button
    const copyMsgBtn = document.getElementById('btn-copy-share-msg');
    if (copyMsgBtn) {
      copyMsgBtn.addEventListener('click', async () => {
        const text = document.getElementById('share-message-preview')?.textContent || '';
        if (text) {
          await copyToClipboard(text);
          const originalText = copyMsgBtn.innerHTML;
          const lang = document.documentElement.lang || 'en';
          let copiedLabel = 'Copied!';
          if (lang.startsWith('ru')) copiedLabel = 'Скопировано!';
          else if (lang.startsWith('pl')) copiedLabel = 'Skopiowano!';
          copyMsgBtn.innerHTML = `<i class="bi bi-check-lg me-1"></i>${copiedLabel}`;
          copyMsgBtn.classList.remove('btn-outline-primary');
          copyMsgBtn.classList.add('btn-success');
          setTimeout(() => {
            copyMsgBtn.innerHTML = originalText;
            copyMsgBtn.classList.remove('btn-success');
            copyMsgBtn.classList.add('btn-outline-primary');
          }, 2000);
        }
      });
    }

    // Copy Link Button
    const copyLinkBtn = document.getElementById('btn-copy-share-link');
    if (copyLinkBtn) {
      copyLinkBtn.addEventListener('click', async () => {
        if (activeLink) {
          await copyToClipboard(activeLink);
          const originalText = copyLinkBtn.innerHTML;
          const lang = document.documentElement.lang || 'en';
          let copiedLabel = 'Copied!';
          if (lang.startsWith('ru')) copiedLabel = 'Скопировано!';
          else if (lang.startsWith('pl')) copiedLabel = 'Skopiowano!';
          copyLinkBtn.innerHTML = `<i class="bi bi-check-lg me-1"></i>${copiedLabel}`;
          copyLinkBtn.classList.remove('btn-outline-secondary');
          copyLinkBtn.classList.add('btn-success');
          setTimeout(() => {
            copyLinkBtn.innerHTML = originalText;
            copyLinkBtn.classList.remove('btn-success');
            copyLinkBtn.classList.add('btn-outline-secondary');
          }, 2000);
        }
      });
    }
  }

  function initOnboardingLinkGenerator(root) {
    const buttons = root.querySelectorAll('.btn-generate-onboarding-link');
    const alertContainer = document.getElementById('ajax-alert-container');
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

    function showAlert(message, type = 'success') {
      if (!alertContainer) return;

      const alert = document.createElement('div');
      alert.className = `alert alert-${type} alert-dismissible fade show mt-2`;
      alert.role = 'alert';
      alert.textContent = message;

      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'btn-close';
      closeBtn.setAttribute('data-bs-dismiss', 'alert');

      const lang = document.documentElement.lang || 'en';
      let closeLabel = 'Close';
      if (lang.startsWith('ru')) closeLabel = '\u0417\u0430\u043a\u0440\u044b\u0442\u044c';
      else if (lang.startsWith('pl')) closeLabel = 'Zamknij';
      closeBtn.setAttribute('aria-label', closeLabel);

      alert.appendChild(closeBtn);
      alertContainer.appendChild(alert);

      setTimeout(() => {
        const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
        if (bsAlert) bsAlert.close();
      }, 3500);
    }

    buttons.forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.preventDefault();
        const url = btn.dataset.generateUrl;
        if (!url) return;

        btn.disabled = true;
        const icon = btn.querySelector('i');
        const originalClass = icon ? icon.className : '';
        if (icon) {
          icon.className = 'spinner-border spinner-border-sm';
        }

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
          const generatedLink = parseGeneratedLinkResponse(data);
          if (icon) {
            icon.className = 'bi bi-check-lg';
            btn.classList.remove('btn-outline-success');
            btn.classList.add('btn-success');
          }

          openShareModal(generatedLink);

          setTimeout(() => {
            if (icon) {
              icon.className = originalClass;
              btn.classList.remove('btn-success');
              btn.classList.add('btn-outline-success');
            }
            btn.disabled = false;
          }, 2000);
        } catch (error) {
          console.error(error);
          if (icon) {
            icon.className = originalClass;
          }
          btn.disabled = false;

          const lang = document.documentElement.lang || 'en';
          let errMsg = 'Failed to generate link. Please try again.';
          if (lang.startsWith('ru')) errMsg = '\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443.';
          else if (lang.startsWith('pl')) errMsg = 'Nie uda\u0142o si\u0119 wygenerowa\u0107 linku.';

          showAlert(errMsg, 'danger');
        }
      });
    });
  }

  function initPublicIntakeLink(root) {
    const btn = root.getElementById('btn-public-intake-link');
    if (!btn) return;

    const alertContainer = document.getElementById('ajax-alert-container');
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const purposeSelect = root.getElementById('quick-onboarding-purpose');
    const modalEl = root.getElementById('quickOnboardingModal');
    const modal = modalEl && window.bootstrap ? bootstrap.Modal.getOrCreateInstance(modalEl) : null;

    function showAlert(message, type = 'success') {
      if (!alertContainer) return;
      const alert = document.createElement('div');
      alert.className = `alert alert-${type} alert-dismissible fade show mt-2`;
      alert.role = 'alert';
      alert.textContent = message;

      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'btn-close';
      closeBtn.setAttribute('data-bs-dismiss', 'alert');
      closeBtn.setAttribute('aria-label', 'Close');
      alert.appendChild(closeBtn);
      alertContainer.appendChild(alert);

      setTimeout(() => {
        const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
        if (bsAlert) bsAlert.close();
      }, 3500);
    }

    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const url = btn.dataset.generateUrl;
      if (!url) return;

      btn.disabled = true;
      const icon = btn.querySelector('i');
      const originalClass = icon ? icon.className : '';
      if (icon) {
        icon.className = 'spinner-border spinner-border-sm';
      }

      try {
        const formData = new FormData();
        if (purposeSelect && purposeSelect.value) {
          formData.append('application_purpose', purposeSelect.value);
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
        const generatedLink = parseGeneratedLinkResponse(data);
        if (icon) {
          icon.className = 'bi bi-check-lg';
          btn.classList.remove('btn-outline-primary');
          btn.classList.add('btn-success');
        }

        if (modal && modalEl.classList.contains('show')) {
          modalEl.addEventListener('hidden.bs.modal', () => {
            openShareModal(generatedLink, 'intake');
          }, { once: true });
          modal.hide();
        } else {
          openShareModal(generatedLink, 'intake');
        }

        setTimeout(() => {
          if (icon) {
            icon.className = originalClass;
            btn.classList.remove('btn-success');
            btn.classList.add('btn-outline-primary');
          }
          btn.disabled = false;
        }, 1500);
      } catch (error) {
        console.error(error);
        if (icon) {
          icon.className = originalClass;
        }
        btn.disabled = false;
        showAlert('Failed to generate intake link. Please try again.', 'danger');
      }
    });
  }

  function initQuickOnboardingLink(root) {
    const btn = root.getElementById('btn-quick-onboarding-link');
    if (!btn) return;

    const alertContainer = document.getElementById('ajax-alert-container');
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const purposeSelect = root.getElementById('quick-onboarding-purpose');
    const modalEl = root.getElementById('quickOnboardingModal');
    const modal = modalEl && window.bootstrap ? bootstrap.Modal.getOrCreateInstance(modalEl) : null;

    function showAlert(message, type = 'success') {
      if (!alertContainer) return;
      const alert = document.createElement('div');
      alert.className = `alert alert-${type} alert-dismissible fade show mt-2`;
      alert.role = 'alert';
      alert.textContent = message;

      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'btn-close';
      closeBtn.setAttribute('data-bs-dismiss', 'alert');

      const lang = document.documentElement.lang || 'en';
      let closeLabel = 'Close';
      if (lang.startsWith('ru')) closeLabel = '\u0417\u0430\u043a\u0440\u044b\u0442\u044c';
      else if (lang.startsWith('pl')) closeLabel = 'Zamknij';
      closeBtn.setAttribute('aria-label', closeLabel);

      alert.appendChild(closeBtn);
      alertContainer.appendChild(alert);

      setTimeout(() => {
        const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
        if (bsAlert) bsAlert.close();
      }, 3500);
    }

    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const url = btn.dataset.generateUrl;
      if (!url) return;

      btn.disabled = true;
      const icon = btn.querySelector('i');
      const originalClass = icon ? icon.className : '';
      if (icon) {
        icon.className = 'spinner-border spinner-border-sm';
      }

      const intakeTypeSelect = root.getElementById('quick-onboarding-intake-type');

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
        const generatedLink = parseGeneratedLinkResponse(data);
        if (icon) {
          icon.className = 'bi bi-check-lg';
          btn.classList.remove('btn-outline-primary');
          btn.classList.add('btn-success');
        }

        if (modal && modalEl.classList.contains('show')) {
          modalEl.addEventListener('hidden.bs.modal', () => {
            openShareModal(generatedLink);
          }, { once: true });
          modal.hide();
        } else {
          openShareModal(generatedLink);
        }

        setTimeout(() => {
          if (icon) {
            icon.className = originalClass;
            btn.classList.remove('btn-success');
            btn.classList.add('btn-outline-primary');
          }
          btn.disabled = false;

          const shareModalEl = document.getElementById('onboardingShareModal');
          if (shareModalEl) {
            shareModalEl.addEventListener('hidden.bs.modal', () => {
              window.location.reload();
            }, { once: true });
          } else {
            window.location.reload();
          }
        }, 1500);
      } catch (error) {
        console.error(error);
        if (icon) {
          icon.className = originalClass;
        }
        btn.disabled = false;

        const lang = document.documentElement.lang || 'en';
        let errMsg = 'Failed to generate link. Please try again.';
        if (lang.startsWith('ru')) errMsg = '\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443.';
        else if (lang.startsWith('pl')) errMsg = 'Nie uda\u0142o si\u0119 wygenerowa\u0107 linku.';

        showAlert(errMsg, 'danger');
      }
    });
  }

  function initAutocompleteSearch(root) {
    const input = root.getElementById('client-search-input');
    const suggestions = root.getElementById('autocomplete-suggestions');
    if (!input || !suggestions) return;

    let debounceTimer;

    input.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      const query = input.value.trim();
      if (query.length < 2) {
        suggestions.style.display = 'none';
        suggestions.innerHTML = '';
        return;
      }

      debounceTimer = setTimeout(async () => {
        const baseUrl = input.dataset.autocompleteUrl;
        if (!baseUrl) return;

        try {
          const response = await fetch(`${baseUrl}?q=${encodeURIComponent(query)}`, {
            headers: {
              'X-Requested-With': 'XMLHttpRequest',
              'Accept': 'application/json'
            }
          });
          if (!response.ok) throw new Error('Network error');

          const data = await response.json();
          renderSuggestions(data.results);
        } catch (err) {
          console.error('Autocomplete error:', err);
        }
      }, 250);
    });

    // Close suggestions when clicking outside
    document.addEventListener('click', (e) => {
      if (!input.contains(e.target) && !suggestions.contains(e.target)) {
        suggestions.style.display = 'none';
      }
    });

    // Show suggestions when clicking back in input if it has results
    input.addEventListener('focus', () => {
      if (suggestions.children.length > 0) {
        suggestions.style.display = 'block';
      }
    });

    function renderSuggestions(results) {
      suggestions.innerHTML = '';
      if (!results || results.length === 0) {
        suggestions.style.display = 'none';
        return;
      }

      results.forEach((client) => {
        const item = document.createElement('a');
        item.href = client.url;
        item.className = 'dropdown-item d-flex flex-column py-2 border-bottom';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'fw-semibold text-primary';
        nameSpan.textContent = `${client.first_name} ${client.last_name}`;
        item.appendChild(nameSpan);

        if (client.email || client.phone) {
          const detailSpan = document.createElement('span');
          detailSpan.className = 'small text-muted';
          detailSpan.textContent = [client.email, client.phone].filter(Boolean).join(' | ');
          item.appendChild(detailSpan);
        }

        suggestions.appendChild(item);
      });

      suggestions.style.display = 'block';
    }
  }

  function initNewCaseClientPicker(root) {
    const modal = root.getElementById('newCaseClientModal');
    const input = root.getElementById('new-case-client-search');
    const results = root.getElementById('new-case-client-results');
    if (!modal || !input || !results) return;

    let debounceTimer;

    modal.addEventListener('shown.bs.modal', () => {
      input.focus();
    });

    modal.addEventListener('hidden.bs.modal', () => {
      input.value = '';
      results.innerHTML = '';
    });

    input.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      const query = input.value.trim();
      if (query.length < 2) {
        results.innerHTML = '';
        return;
      }

      debounceTimer = setTimeout(async () => {
        const baseUrl = input.dataset.autocompleteUrl;
        if (!baseUrl) return;

        try {
          const response = await fetch(`${baseUrl}?q=${encodeURIComponent(query)}`, {
            headers: {
              'X-Requested-With': 'XMLHttpRequest',
              'Accept': 'application/json'
            }
          });
          if (!response.ok) throw new Error('Network error');

          const data = await response.json();
          renderResults(data.results);
        } catch (err) {
          console.error('New case client picker error:', err);
        }
      }, 250);
    });

    function renderResults(clients) {
      results.innerHTML = '';
      if (!clients || clients.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'list-group-item text-muted small';
        empty.textContent = input.dataset.emptyLabel || '';
        results.appendChild(empty);
        return;
      }

      clients.forEach((client) => {
        const item = document.createElement('a');
        item.href = client.case_add_url;
        item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center gap-2';

        const info = document.createElement('div');
        info.className = 'd-flex flex-column';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'fw-semibold';
        nameSpan.textContent = `${client.first_name} ${client.last_name}`;
        info.appendChild(nameSpan);

        if (client.email || client.phone) {
          const detailSpan = document.createElement('span');
          detailSpan.className = 'small text-muted';
          detailSpan.textContent = [client.email, client.phone].filter(Boolean).join(' | ');
          info.appendChild(detailSpan);
        }
        item.appendChild(info);

        const count = client.active_cases_count || 0;
        const badge = document.createElement('span');
        badge.className = count > 0 ? 'badge bg-warning text-dark' : 'badge bg-secondary';
        badge.textContent = `${input.dataset.casesLabel || ''}: ${count}`;
        item.appendChild(badge);

        results.appendChild(item);
      });
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    enhanceEditors(document);
    initOnboardingLinkGenerator(document);
    initPublicIntakeLink(document);
    initQuickOnboardingLink(document);
    initAutocompleteSearch(document);
    initNewCaseClientPicker(document);
    initShareModalListeners();
  });
})();

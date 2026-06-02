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
    const boldButton = root.querySelector('[data-notes-bold]');

    function updateIndicator() {
      if (!boldIndicator) {
        return;
      }
      boldIndicator.style.display = selectionHasBold() ? 'inline-block' : 'none';
    }

    if (boldButton) {
      boldButton.addEventListener('click', (event) => {
        event.preventDefault();
        toggleBoldSelection();
        updateIndicator();
      });
    }

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
          if (data.status === 'ok') {
            await copyToClipboard(data.link);
            
            if (icon) {
              icon.className = 'bi bi-check-lg';
              btn.classList.remove('btn-outline-success');
              btn.classList.add('btn-success');
            }
            
            const msg = data.message || 'Onboarding link copied!';
            showAlert(msg, 'success');

            setTimeout(() => {
              if (icon) {
                icon.className = originalClass;
                btn.classList.remove('btn-success');
                btn.classList.add('btn-outline-success');
              }
              btn.disabled = false;
            }, 2000);
          } else {
            throw new Error(data.message || 'Generation failed');
          }
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
        if (data.status === 'ok') {
          await copyToClipboard(data.link);
          
          if (icon) {
            icon.className = 'bi bi-check-lg';
            btn.classList.remove('btn-outline-primary');
            btn.classList.add('btn-success');
          }
          
          const msg = data.message || 'Onboarding link copied!';
          if (modal) {
            modal.hide();
          }
          showAlert(msg, 'success');

          setTimeout(() => {
            if (icon) {
              icon.className = originalClass;
              btn.classList.remove('btn-success');
              btn.classList.add('btn-outline-primary');
            }
            btn.disabled = false;
            window.location.reload();
          }, 1500);
        } else {
          throw new Error(data.message || 'Generation failed');
        }
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

  document.addEventListener('DOMContentLoaded', () => {
    enhanceEditors(document);
    initOnboardingLinkGenerator(document);
    initQuickOnboardingLink(document);
    initAutocompleteSearch(document);
  });
})();

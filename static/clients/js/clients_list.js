(function () {
  const PLACEHOLDER_TEXT = 'None';

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

  document.addEventListener('DOMContentLoaded', () => {
    enhanceEditors(document);
  });
})();

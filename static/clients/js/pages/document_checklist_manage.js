(function() {
  'use strict';

  const container = document.getElementById('draggableChecklistContainer');
  if (!container) return;

  let draggedEl = null;
  let placeholder = null;

  function createPlaceholder() {
    const ph = document.createElement('div');
    ph.className = 'col drag-placeholder';
    ph.style.pointerEvents = 'none';
    return ph;
  }

  function getClosestAfter(container, y) {
    const items = [...container.querySelectorAll('.draggable-item:not(.dragging)')];
    let closest = null;
    let closestOffset = Number.NEGATIVE_INFINITY;
    items.forEach(item => {
      const box = item.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closestOffset) {
        closestOffset = offset;
        closest = item;
      }
    });
    return closest;
  }

  function updatePositionBadges() {
    const items = container.querySelectorAll('.draggable-item');
    items.forEach((item, idx) => {
      let badge = item.querySelector('.position-badge');
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'position-badge';
        const flex = item.querySelector('.d-flex.align-items-center.flex-grow-1');
        if (flex) flex.insertBefore(badge, flex.firstChild);
      }
      badge.textContent = idx + 1;
    });
  }

  function syncHiddenOrderInputs() {
    const existing = container.closest('form').querySelectorAll('input[name="doc_order"]');
    existing.forEach(el => el.remove());
    const items = container.querySelectorAll('.draggable-item');
    const form = container.closest('form');
    items.forEach((item, idx) => {
      const checkbox = item.querySelector('input[type="checkbox"]');
      if (checkbox) {
        const hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'doc_order';
        hidden.value = checkbox.value;
        form.appendChild(hidden);
      }
    });
  }

  // Touch support variables
  let touchItem = null;
  let touchClone = null;
  let touchStartY = 0;
  let touchStartX = 0;

  // --- Mouse/Pointer Drag & Drop ---
  container.addEventListener('dragstart', function(e) {
    const item = e.target.closest('.draggable-item');
    if (!item) return;
    draggedEl = item;
    item.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', '');
    placeholder = createPlaceholder();
  });

  container.addEventListener('dragover', function(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (!draggedEl) return;
    const afterEl = getClosestAfter(container, e.clientY);
    if (placeholder.parentNode) placeholder.parentNode.removeChild(placeholder);
    if (afterEl) {
      container.insertBefore(placeholder, afterEl);
    } else {
      container.appendChild(placeholder);
    }
  });

  container.addEventListener('drop', function(e) {
    e.preventDefault();
    if (!draggedEl || !placeholder) return;
    container.insertBefore(draggedEl, placeholder);
    if (placeholder.parentNode) placeholder.parentNode.removeChild(placeholder);
    draggedEl.classList.remove('dragging');
    updatePositionBadges();
    syncHiddenOrderInputs();
    draggedEl = null;
    placeholder = null;
  });

  container.addEventListener('dragend', function(e) {
    if (draggedEl) draggedEl.classList.remove('dragging');
    if (placeholder && placeholder.parentNode) placeholder.parentNode.removeChild(placeholder);
    draggedEl = null;
    placeholder = null;
  });

  // --- Touch Drag & Drop ---
  container.addEventListener('touchstart', function(e) {
    const handle = e.target.closest('.drag-handle');
    if (!handle) return;
    const item = handle.closest('.draggable-item');
    if (!item) return;
    touchItem = item;
    const touch = e.touches[0];
    touchStartY = touch.clientY;
    touchStartX = touch.clientX;
    item.classList.add('dragging');
    placeholder = createPlaceholder();
    container.insertBefore(placeholder, item.nextSibling);
  }, { passive: true });

  container.addEventListener('touchmove', function(e) {
    if (!touchItem) return;
    e.preventDefault();
    const touch = e.touches[0];
    const afterEl = getClosestAfter(container, touch.clientY);
    if (placeholder.parentNode) placeholder.parentNode.removeChild(placeholder);
    if (afterEl) {
      container.insertBefore(placeholder, afterEl);
    } else {
      container.appendChild(placeholder);
    }
  }, { passive: false });

  container.addEventListener('touchend', function(e) {
    if (!touchItem) return;
    if (placeholder && placeholder.parentNode) {
      container.insertBefore(touchItem, placeholder);
      placeholder.parentNode.removeChild(placeholder);
    }
    touchItem.classList.remove('dragging');
    updatePositionBadges();
    syncHiddenOrderInputs();
    touchItem = null;
    placeholder = null;
  });

  // Initial setup
  updatePositionBadges();
  syncHiddenOrderInputs();
})();

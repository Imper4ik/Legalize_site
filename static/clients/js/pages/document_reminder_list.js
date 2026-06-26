// Если захочешь flatpickr для более приятного выбора дат — раскомментируй блок ниже.
    // document.addEventListener('DOMContentLoaded', function () {
    //   if (window.flatpickr) {
    //     flatpickr('#doc_start_date', { dateFormat: 'Y-m-d' });
    //     flatpickr('#doc_end_date',   { dateFormat: 'Y-m-d' });
    //   }
    // });
    document.addEventListener('DOMContentLoaded', function () {
      var hash = window.location.hash;
      if (!hash || !hash.startsWith('#heading-')) {
        return;
      }
      var headingElement = document.querySelector(hash);
      if (!headingElement || !window.bootstrap || !window.bootstrap.Collapse) {
        return;
      }
      var toggleButton = headingElement.querySelector('[data-bs-toggle="collapse"]');
      if (!toggleButton) {
        return;
      }
      var targetSelector = toggleButton.getAttribute('data-bs-target');
      var collapseElement = targetSelector ? document.querySelector(targetSelector) : null;
      if (!collapseElement) {
        return;
      }
      var collapse = new window.bootstrap.Collapse(collapseElement, { toggle: false });
      collapse.show();
    });

(function () {

  // Filter history entries by free text.
  var filter = document.getElementById("historyFilter");
  if (filter) {
    filter.addEventListener("input", function () {
      var q = filter.value.trim().toLowerCase();
      var anyVisible = false;
      document.querySelectorAll("#historyList .history-item").forEach(function (item) {
        var match = item.textContent.toLowerCase().indexOf(q) !== -1;
        item.style.display = match ? "" : "none";
        if (match) anyVisible = true;
      });
      var noMatch = document.getElementById("historyNoMatch");
      if (noMatch) noMatch.classList.toggle("d-none", anyVisible || q === "");
    });
  }

  // Populate and open the Edit Payment modal from a row's data-* attributes.
  var editForm = document.getElementById("caseEditPaymentForm");
  function setVal(selector, value) {
    var el = editForm.querySelector(selector);
    if (el) el.value = value || "";
  }
  document.querySelectorAll(".js-edit-payment").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (!editForm) return;
      editForm.setAttribute("action", btn.getAttribute("data-action"));
      setVal('[data-edit="service"]', btn.getAttribute("data-service"));
      setVal('[data-edit="total"]', btn.getAttribute("data-total"));
      setVal('[data-edit="paid"]', btn.getAttribute("data-paid"));
      setVal('[data-edit="status"]', btn.getAttribute("data-status"));
      setVal('[data-edit="method"]', btn.getAttribute("data-method"));
      setVal('[data-edit="due"]', btn.getAttribute("data-due"));
      new bootstrap.Modal(document.getElementById("caseEditPaymentModal")).show();
    });
  });

  // Upload control: the visible button opens the hidden file picker; selecting
  // a file submits the form immediately, so it behaves like the other row
  // action buttons (no separate file/date bar). OCR determines the ZUS month.
  document.querySelectorAll(".js-case-upload-trigger").forEach(function (btn) {
    var form = btn.closest(".js-case-upload-form");
    if (!form) return;
    var input = form.querySelector(".js-case-upload-input");
    if (!input) return;
    btn.addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () {
      if (input.files && input.files.length > 0) {
        if (typeof form.requestSubmit === "function") { form.requestSubmit(); }
        else { form.submit(); }
      }
    });
  });

  // Keep the active tab across reloads and post-action redirects by mirroring it
  // in the URL hash. Without this a refresh (or an upload/delete redirect) always
  // snapped back to the Overview tab.
  var tabButtons = document.querySelectorAll('#caseTabs button[data-bs-toggle="tab"]');
  if (tabButtons.length && window.bootstrap && bootstrap.Tab) {
    var hash = window.location.hash;
    if (hash) {
      var target = document.querySelector('#caseTabs button[data-bs-target="' + hash + '"]');
      if (target) { bootstrap.Tab.getOrCreateInstance(target).show(); }
    }
    tabButtons.forEach(function (btn) {
      btn.addEventListener("shown.bs.tab", function (event) {
        var id = event.target.getAttribute("data-bs-target");
        if (id) { history.replaceState(null, "", id); }
      });
    });
  }
})();

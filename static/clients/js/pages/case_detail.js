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
})();

// Make the checklist status badges ("OCR-проверка" / "Ждёт проверки") lead
// straight to the document that needs attention: expand its accordion row,
// scroll to and highlight the file, and for OCR open its review dialog.
(function () {
  "use strict";

  function expandAccordion(target) {
    var item = target.closest(".accordion-item");
    if (!item) return;
    var collapse = item.querySelector(".accordion-collapse");
    if (!collapse) return;
    if (window.bootstrap && window.bootstrap.Collapse) {
      window.bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false }).show();
    } else {
      collapse.classList.add("show");
    }
  }

  function jump(badge) {
    var docId = badge.getAttribute("data-jump-doc");
    if (!docId) return;
    expandAccordion(badge);

    var row = document.getElementById("doc-row-" + docId);
    // The collapse animation needs a tick before the row has a layout box.
    window.setTimeout(function () {
      if (row) {
        row.scrollIntoView({ behavior: "smooth", block: "center" });
        row.classList.add("attention-flash");
        window.setTimeout(function () {
          row.classList.remove("attention-flash");
        }, 1600);
      }
      if (badge.getAttribute("data-jump-action") === "ocr") {
        var reviewBtn = document.querySelector(
          '.review-ocr-data-btn[data-doc-id="' + docId + '"]'
        );
        if (reviewBtn) reviewBtn.click();
      }
    }, 380);
  }

  document.addEventListener("click", function (event) {
    var badge = event.target.closest(".checklist-jump[data-jump-doc]");
    if (!badge) return;
    // Don't let the click also toggle the accordion header it sits inside.
    event.preventDefault();
    event.stopPropagation();
    jump(badge);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    var badge = event.target.closest(".checklist-jump[data-jump-doc]");
    if (!badge) return;
    event.preventDefault();
    event.stopPropagation();
    jump(badge);
  });
})();

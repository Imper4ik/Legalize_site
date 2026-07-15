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

  function jumpToDocument(docId, action) {
    if (!docId) return;

    var row = document.getElementById("doc-row-" + docId);
    if (!row) return;
    expandAccordion(row);
    // The collapse animation needs a tick before the row has a layout box.
    window.setTimeout(function () {
      if (row) {
        row.scrollIntoView({ behavior: "smooth", block: "center" });
        row.classList.add("attention-flash");
        window.setTimeout(function () {
          row.classList.remove("attention-flash");
        }, 1600);
      }
      if (action === "ocr") {
        var reviewBtn = document.querySelector(
          '.review-ocr-data-btn[data-doc-id="' + docId + '"]'
        );
        if (reviewBtn) reviewBtn.click();
      }
    }, 380);
  }

  function jump(badge) {
    jumpToDocument(
      badge.getAttribute("data-jump-doc"),
      badge.getAttribute("data-jump-action")
    );
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

  function handleDocumentHash() {
    var match = window.location.hash.match(/^#doc-row-(\d+)$/);
    if (!match) return;
    var row = document.getElementById("doc-row-" + match[1]);
    if (!row) return;
    var pane = row.closest(".tab-pane");
    if (pane && pane.id) {
      var trigger = document.querySelector('[data-bs-target="#' + pane.id + '"]');
      if (trigger && window.bootstrap && window.bootstrap.Tab) {
        window.bootstrap.Tab.getOrCreateInstance(trigger).show();
      } else if (trigger) {
        trigger.click();
      }
    }
    jumpToDocument(match[1], "warning");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", handleDocumentHash);
  } else {
    handleDocumentHash();
  }
})();

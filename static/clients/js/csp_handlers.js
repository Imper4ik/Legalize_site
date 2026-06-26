// CSP-safe delegated handlers replacing inline on*= attributes, so the page
// carries no inline JavaScript. Behaviour matches the old inline handlers:
//   <form data-confirm="msg">         -> confirm() before submit
//   <button data-confirm="msg">       -> confirm() before the button's action
//   <… data-print>                    -> window.print()
//   <… data-copy-target="elementId">  -> copy that input's value to clipboard
(function () {
  // Confirm-before-submit for forms.
  document.addEventListener(
    "submit",
    function (e) {
      var form = e.target.closest && e.target.closest("form[data-confirm]");
      if (form && !window.confirm(form.getAttribute("data-confirm"))) {
        e.preventDefault();
      }
    },
    true
  );

  document.addEventListener("click", function (e) {
    if (!e.target.closest) return;

    // Confirm-before-action for buttons/links (not forms, handled above).
    var confirmEl = e.target.closest("[data-confirm]");
    if (confirmEl && confirmEl.tagName !== "FORM") {
      if (!window.confirm(confirmEl.getAttribute("data-confirm"))) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
    }

    var printEl = e.target.closest("[data-print]");
    if (printEl) {
      e.preventDefault();
      window.print();
      return;
    }

    var copyEl = e.target.closest("[data-copy-target]");
    if (copyEl) {
      var target = document.getElementById(copyEl.getAttribute("data-copy-target"));
      if (target && target.value && navigator.clipboard) {
        navigator.clipboard.writeText(target.value);
      }
    }
  });
})();

// Make "attention" / health-alert action links work across tabs.
//
// Alert actions point at anchors like #documentAccordion or #payment-list-container
// that live inside a Bootstrap tab pane. Jumping to such an anchor does nothing
// visible while the owning tab is inactive, so the user "doesn't see what to do".
// This activates the owning tab first, then scrolls the target into view — both
// on click and when the page is opened with a matching #hash.
(function () {
  "use strict";

  function activateTabFor(target) {
    if (!target) return false;
    var pane = target.closest(".tab-pane");
    if (!pane || !pane.id) return false;
    var trigger = document.querySelector('[data-bs-target="#' + pane.id + '"]');
    if (!trigger) return false;
    if (window.bootstrap && window.bootstrap.Tab) {
      window.bootstrap.Tab.getOrCreateInstance(trigger).show();
    } else {
      trigger.click();
    }
    return true;
  }

  function resolveTarget(hash) {
    if (!hash || hash.charAt(0) !== "#" || hash.length < 2) return null;
    try {
      return document.getElementById(decodeURIComponent(hash.slice(1)));
    } catch (e) {
      return null;
    }
  }

  function scrollIntoView(target) {
    if (!target) return;
    window.requestAnimationFrame(function () {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      target.classList.add("attention-flash");
      window.setTimeout(function () {
        target.classList.remove("attention-flash");
      }, 1600);
    });
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest('a[href^="#"]');
    if (!link) return;
    var hash = link.getAttribute("href");
    if (!hash || hash === "#") return;
    var target = resolveTarget(hash);
    if (target && activateTabFor(target)) {
      event.preventDefault();
      scrollIntoView(target);
    }
  });

  function handleInitialHash() {
    var target = resolveTarget(window.location.hash);
    if (target && activateTabFor(target)) {
      scrollIntoView(target);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", handleInitialHash);
  } else {
    handleInitialHash();
  }
})();

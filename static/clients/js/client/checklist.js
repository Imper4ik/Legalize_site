const CHECKLIST_REFRESH_INTERVAL_MS = 30000;

let refreshChecklist = null;
let pauseChecklistRefreshUntil = 0;
function pauseChecklistRefresh(duration = 3000) {
  pauseChecklistRefreshUntil = Math.max(pauseChecklistRefreshUntil, Date.now() + duration);
}
function initChecklistRefresher() {
  const accordion = document.getElementById('documentAccordion');
  if (!accordion) {
    return;
  }

  const refreshUrl = accordion.dataset.refreshUrl;
  if (!refreshUrl) {
    return;
  }

  let controller = null;
  let isFetching = false;
  let checklistTransitionInProgress = false;

  function restoreExpandedPanels(ids) {
    ids.forEach((id) => {
      const collapseEl = accordion.querySelector(`#${id}`);
      if (!collapseEl) {
        return;
      }
      const instance = bootstrap.Collapse.getOrCreateInstance(collapseEl, { toggle: false });
      instance.show();
      const trigger = accordion.querySelector(`[data-bs-target="#${id}"]`);
      if (trigger) {
        trigger.classList.remove('collapsed');
        trigger.setAttribute('aria-expanded', 'true');
      }
    });
  }

  async function refresh({ force = false } = {}) {
    const hasOpenModal = Boolean(document.querySelector('.modal.show'));
    const isUserInteracting = accordion.contains(document.activeElement);
    const isTransitioning = checklistTransitionInProgress || accordion.querySelector('.collapsing');

    // Do not refresh checklist while Bootstrap accordion is transitioning; replacing DOM during collapse animations causes visible UI jank.
    if (
      !force
      && (isFetching
        || document.visibilityState !== 'visible'
        || hasOpenModal
        || isUserInteracting
        || isTransitioning
        || Date.now() < pauseChecklistRefreshUntil)
    ) {
      return;
    }

    const expanded = Array.from(accordion.querySelectorAll('.accordion-collapse.show')).map((panel) => panel.id);

    if (controller) {
      controller.abort();
    }
    controller = new AbortController();
    isFetching = true;

    try {
      const { html } = await fetchHtml(refreshUrl, {
        cache: 'no-store',
        signal: controller.signal,
      });
      const trimmedHtml = html.trim();
      if (!trimmedHtml || accordion.innerHTML.trim() === trimmedHtml) {
        return;
      }

      replaceNodeContents(accordion, trimmedHtml);
      restoreExpandedPanels(expanded);
    } catch (error) {
      if (error.name !== 'AbortError') {
        logAjaxError('refresh checklist', error, { url: refreshUrl });
      }
    } finally {
      isFetching = false;
    }
  }

  refreshChecklist = refresh;

  let intervalId = null;

  function startInterval() {
    if (intervalId === null) {
      intervalId = window.setInterval(refresh, CHECKLIST_REFRESH_INTERVAL_MS);
    }
  }

  function stopInterval() {
    if (intervalId !== null) {
      window.clearInterval(intervalId);
      intervalId = null;
    }
    if (controller) {
      controller.abort();
    }
  }

  document.addEventListener('show.bs.modal', stopInterval);
  document.addEventListener('hidden.bs.modal', () => {
    if (!document.querySelector('.modal.show')) {
      startInterval();
    }
  });

  document.addEventListener('visibilitychange', refresh);
  accordion.addEventListener('show.bs.collapse', () => {
    checklistTransitionInProgress = true;
    accordion.classList.add('is-checklist-transitioning');
    pauseChecklistRefresh(10000);
  });
  accordion.addEventListener('shown.bs.collapse', () => {
    checklistTransitionInProgress = false;
    accordion.classList.remove('is-checklist-transitioning');
    pauseChecklistRefresh(10000);
  });
  accordion.addEventListener('hide.bs.collapse', () => {
    checklistTransitionInProgress = true;
    accordion.classList.add('is-checklist-transitioning');
    pauseChecklistRefresh(5000);
  });
  accordion.addEventListener('hidden.bs.collapse', () => {
    checklistTransitionInProgress = false;
    accordion.classList.remove('is-checklist-transitioning');
  });
  accordion.addEventListener('focusin', () => {
    pauseChecklistRefresh(10000);
  });
  accordion.addEventListener('pointerdown', () => {
    pauseChecklistRefresh(10000);
  });
  window.addEventListener('beforeunload', () => {
    stopInterval();
    document.removeEventListener('show.bs.modal', stopInterval);
  });

  startInterval();
}

document.addEventListener("DOMContentLoaded", function() {
    const form = document.querySelector("form[data-onboarding-autosave]") || document.querySelector(".page-surface form");
    if (!form || !window.ONBOARDING_AUTO_SAVE_URL) return;

    const controls = Array.from(form.querySelectorAll("input, select, textarea")).filter(input => {
        return input.type !== "hidden" && input.type !== "file" && input.name !== "csrfmiddlewaretoken";
    });
    if (!controls.length) return;

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrfToken = getCookie('csrftoken') || form.querySelector('[name=csrfmiddlewaretoken]')?.value;
    const statusEl = document.createElement("div");
    statusEl.className = "small text-muted mb-3";
    statusEl.setAttribute("aria-live", "polite");
    form.prepend(statusEl);

    function setStatus(message, className) {
        statusEl.textContent = message || "";
        statusEl.className = className || "small text-muted mb-3";
    }

    function saveDraft(options = {}) {
        const formData = new FormData(form);
        if (!options.silent) {
            setStatus("Saving...", "small text-muted mb-3");
        }

        return fetch(window.ONBOARDING_AUTO_SAVE_URL, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest"
            },
            body: formData,
            keepalive: Boolean(options.keepalive)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error("HTTP error " + response.status);
            }
            return response.json();
        })
        .then(data => {
            if (!options.silent) {
                const savedAt = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
                setStatus("Saved " + savedAt, "small text-success mb-3");
            }
            return data;
        })
        .catch(error => {
            if (!options.silent) {
                setStatus("Save failed. Check your connection.", "small text-danger mb-3");
            }
            console.error("Error auto-saving draft:", error);
        });
    }

    let timeout = null;
    function debouncedSave() {
        clearTimeout(timeout);
        timeout = setTimeout(saveDraft, 1000);
    }

    function flushDraft() {
        clearTimeout(timeout);
        const formData = new FormData(form);
        if (navigator.sendBeacon) {
            navigator.sendBeacon(window.ONBOARDING_AUTO_SAVE_URL, formData);
            return;
        }
        saveDraft({ keepalive: true, silent: true });
    }

    controls.forEach(input => {
        if (input.type === "text" || input.type === "date" || input.tagName === "TEXTAREA" || input.type === "password" || input.type === "email" || input.type === "tel") {
            input.addEventListener("input", debouncedSave);
        } else {
            input.addEventListener("change", saveDraft);
        }
    });

    window.addEventListener("pagehide", flushDraft);
    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "hidden") {
            flushDraft();
        }
    });
});

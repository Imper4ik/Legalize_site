document.addEventListener("DOMContentLoaded", function() {
    const form = document.querySelector("form[data-onboarding-autosave]") || document.querySelector(".page-surface form:not([data-no-autosave])");
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
    const statusEl = document.getElementById("autosave-pill");
    const statusDot = document.getElementById("autosave-dot");
    const statusText = document.getElementById("autosave-text");

    const textSaving = statusEl ? (statusEl.getAttribute("data-text-saving") || "Saving...") : "Saving...";
    const textSaved = statusEl ? (statusEl.getAttribute("data-text-saved") || "Saved") : "Saved";
    const textFailed = statusEl ? (statusEl.getAttribute("data-text-failed") || "Save failed. Check your connection.") : "Save failed. Check your connection.";

    let hideTimeout = null;

    function setStatus(message, state) {
        if (!statusEl || !statusDot || !statusText) return;
        
        clearTimeout(hideTimeout);
        
        if (!message) {
            statusEl.classList.remove("visible");
            return;
        }

        statusText.textContent = message;
        statusDot.className = "autosave-dot " + (state || "success");
        statusEl.classList.add("visible");

        if (state === "success") {
            hideTimeout = setTimeout(() => {
                statusEl.classList.remove("visible");
            }, 3000);
        }
    }

    function saveDraft(options = {}) {
        const formData = new FormData(form);
        if (!options.silent) {
            setStatus(textSaving, "saving");
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
                setStatus(textSaved + " " + savedAt, "success");
            }
            return data;
        })
        .catch(error => {
            if (!options.silent) {
                setStatus(textFailed, "danger");
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

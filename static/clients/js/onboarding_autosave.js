document.addEventListener("DOMContentLoaded", function() {
    const form = document.querySelector("form");
    if (!form || !window.ONBOARDING_AUTO_SAVE_URL) return;

    // Helper to get CSRF token
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

    function saveDraft() {
        // Collect form data
        const formData = new FormData(form);
        
        fetch(window.ONBOARDING_AUTO_SAVE_URL, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest"
            },
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error("HTTP error " + response.status);
            }
            return response.json();
        })
        .then(data => {
            console.log("Draft auto-saved successfully:", data);
        })
        .catch(error => {
            console.error("Error auto-saving draft:", error);
        });
    }

    // Debounce function to limit rapid requests (e.g. while typing)
    let timeout = null;
    function debouncedSave() {
        clearTimeout(timeout);
        timeout = setTimeout(saveDraft, 1000); // Wait 1 second after last input activity
    }

    // Listen to change/input/blur events on form controls
    form.querySelectorAll("input, select, textarea").forEach(input => {
        // Use 'input' event for text/date fields so it autosaves as they type (with debounce)
        if (input.type === "text" || input.type === "date" || input.tagName === "TEXTAREA" || input.type === "password" || input.type === "email" || input.type === "tel") {
            input.addEventListener("input", debouncedSave);
        } else {
            // For checkboxes, radios, select dropdowns, save immediately
            input.addEventListener("change", saveDraft);
        }
    });
});

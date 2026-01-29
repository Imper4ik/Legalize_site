// Global Loading Indicator Helper
const LoadingIndicator = {
    show() {
        const loader = document.getElementById('global-loader');
        if (loader) {
            loader.classList.add('active');
        }
    },

    hide() {
        const loader = document.getElementById('global-loader');
        if (loader) {
            loader.classList.remove('active');
        }
    }
};

// Auto-integrate with fetch API
const originalFetch = window.fetch;
window.fetch = function (...args) {
    LoadingIndicator.show();
    return originalFetch.apply(this, args)
        .finally(() => {
            LoadingIndicator.hide();
        });
};

// Expose globally for manual use
window.LoadingIndicator = LoadingIndicator;

// Form validation helper
function validateForm(formElement) {
    const inputs = formElement.querySelectorAll('input[required], select[required], textarea[required]');
    let isValid = true;

    inputs.forEach(input => {
        // Clear previous validation
        input.classList.remove('is-invalid', 'is-valid');
        const feedback = input.parentElement.querySelector('.invalid-feedback');
        if (feedback) {
            feedback.remove();
        }

        // Check validity
        if (!input.checkValidity()) {
            isValid = false;
            input.classList.add('is-invalid');

            // Add feedback message
            const feedbackDiv = document.createElement('div');
            feedbackDiv.className = 'invalid-feedback';
            feedbackDiv.textContent = input.validationMessage;
            input.parentElement.appendChild(feedbackDiv);
        } else if (input.value) {
            input.classList.add('is-valid');
        }
    });

    return isValid;
}

// Attach to all forms on page
document.addEventListener('DOMContentLoaded', () => {
    const forms = document.querySelectorAll('form[data-validate]');

    forms.forEach(form => {
        form.addEventListener('submit', (e) => {
            if (!validateForm(form)) {
                e.preventDefault();
                e.stopPropagation();
            }
        });

        // Real-time validation on blur
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('blur', () => {
                if (input.value) {
                    if (input.checkValidity()) {
                        input.classList.remove('is-invalid');
                        input.classList.add('is-valid');
                        const feedback = input.parentElement.querySelector('.invalid-feedback');
                        if (feedback) feedback.remove();
                    }
                }
            });
        });
    });
});

// Expose validation helper globally
window.validateForm = validateForm;

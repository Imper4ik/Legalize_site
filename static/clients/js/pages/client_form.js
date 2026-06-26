document.addEventListener('DOMContentLoaded', function() {
      const form = document.querySelector('form[data-client-form]');
      if (!form) {
        return;
      }

      const submitButton = form.querySelector('[data-submit-button]');
      const spinner = submitButton ? submitButton.querySelector('[data-spinner]') : null;
      const buttonText = submitButton ? submitButton.querySelector('[data-button-text]') : null;
      const defaultText = submitButton ? submitButton.getAttribute('data-default-text') : null;
      const loadingText = submitButton ? submitButton.getAttribute('data-loading-text') : null;

      const showSpinner = () => {
        if (!submitButton || !spinner || !buttonText) {
          return;
        }
        submitButton.disabled = true;
        spinner.classList.remove('d-none');
        buttonText.textContent = loadingText || buttonText.textContent;
      };

      const hideSpinner = () => {
        if (!submitButton || !spinner || !buttonText) {
          return;
        }
        submitButton.disabled = false;
        spinner.classList.add('d-none');
        buttonText.textContent = defaultText || buttonText.textContent;
      };

      const markInvalidFields = () => {
        const invalidFields = form.querySelectorAll(':invalid');
        invalidFields.forEach((field) => {
          field.classList.add('is-invalid');
        });
        if (invalidFields.length) {
          invalidFields[0].focus();
        }
      };

      // Highlight any server-side errors on initial render
      form.querySelectorAll('.invalid-feedback').forEach((feedback) => {
        const container = feedback.parentElement;
        if (!container) {
          return;
        }
        const formField = container.querySelector('input, select, textarea');
        if (formField && feedback.textContent.trim().length) {
          formField.classList.add('is-invalid');
        }
      });

      form.addEventListener('submit', function(event) {
        // Remove previous invalid styling so we can re-evaluate
        form.querySelectorAll('.is-invalid').forEach((el) => el.classList.remove('is-invalid'));

        if (!form.checkValidity()) {
          event.preventDefault();
          event.stopPropagation();
          hideSpinner();
          markInvalidFields();
          return;
        }

        showSpinner();
      });

      form.addEventListener('input', function(event) {
        const target = event.target;
        if (target.classList.contains('is-invalid') && target.checkValidity()) {
          target.classList.remove('is-invalid');
        }
      }, true);

      form.addEventListener('invalid', function(event) {
        const target = event.target;
        target.classList.add('is-invalid');
      }, true);
    });

document.addEventListener('DOMContentLoaded', function() {
      const params = new URLSearchParams(window.location.search);
      const purposeSelect = document.getElementById('id_application_purpose');
      const roleSelect = document.getElementById('id_family_role');
      const sponsorSelect = document.getElementById('id_sponsor_client');
      const familyFields = document.querySelectorAll('[data-family-only-field]');
      const sponsorField = document.getElementById('family-sponsor-field');

      /* --- Sponsor-role help text (injected once) --- */
      let sponsorHelpText = document.getElementById('sponsor-role-help-text');
      if (!sponsorHelpText && sponsorField) {
        sponsorHelpText = document.createElement('div');
        sponsorHelpText.id = 'sponsor-role-help-text';
        sponsorHelpText.className = 'form-text text-info d-none';
        sponsorHelpText.textContent = 'Спонсор семьи использует рабочий чеклист документов.';
        const roleFieldEl = document.getElementById('family-role-field');
        if (roleFieldEl) {
          roleFieldEl.appendChild(sponsorHelpText);
        }
      }

      if (purposeSelect && params.get('application_purpose') && !purposeSelect.value) {
        purposeSelect.value = params.get('application_purpose');
      }
      if (purposeSelect && params.get('application_purpose') === 'family') {
        purposeSelect.value = 'family';
      }
      if (sponsorSelect && params.get('sponsor')) {
        sponsorSelect.value = params.get('sponsor');
      }

      function updateFamilyFields() {
        const isFamily = purposeSelect && purposeSelect.value === 'family';
        const role = roleSelect ? roleSelect.value : '';
        const needsSponsor = isFamily && ['family_spouse', 'family_child'].includes(role);

        /* Show / hide all family-only fields (role + sponsor container) */
        familyFields.forEach((field) => {
          field.classList.toggle('d-none', !isFamily);
        });

        /* Role is required whenever purpose is family */
        if (roleSelect) {
          roleSelect.required = Boolean(isFamily);
        }

        /* Sponsor field: visible only when spouse / child is selected */
        if (sponsorField) {
          sponsorField.classList.toggle('d-none', !needsSponsor);
        }

        /* Sponsor select: required only for spouse / child */
        if (sponsorSelect) {
          sponsorSelect.required = needsSponsor;

          /* Safe clearing: only clear when not family, or role is sponsor.
             Never clear when role is spouse/child (preserves add-relative prefill). */
          if (!isFamily || role === 'sponsor') {
            sponsorSelect.value = '';
          }
        }

        /* Help text for sponsor role */
        if (sponsorHelpText) {
          sponsorHelpText.classList.toggle('d-none', !(isFamily && role === 'sponsor'));
        }
      }

      if (purposeSelect) {
        purposeSelect.addEventListener('change', updateFamilyFields);
      }
      if (roleSelect) {
        roleSelect.addEventListener('change', updateFamilyFields);
      }
      updateFamilyFields();
    });

document.addEventListener('DOMContentLoaded', function() {
        function setupFlatpickr(inputId, buttonId) {
            const input = document.getElementById(inputId);
            const button = document.getElementById(buttonId);

            if (input && button) {
                const calendar = flatpickr(input, {
                    dateFormat: "d.m.Y",
                    allowInput: true,
                    clickOpens: false
                });
                button.addEventListener('click', function() { calendar.toggle(); });
            }
        }
        setupFlatpickr('id_legal_basis_end_date', 'toggle_legal_basis_end_date');
    });

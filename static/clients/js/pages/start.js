document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".onboarding-upload-form").forEach(function (form) {
    const input = form.querySelector(".onboarding-upload-input");
    const confirmBox = form.querySelector(".onboarding-upload-confirm");
    const submit = form.querySelector(".onboarding-upload-submit");
    const box = form.querySelector(".onboarding-upload-preview");
    const nameEl = form.querySelector("[data-file-name]");
    const img = form.querySelector("[data-image-preview]");
    const pdf = form.querySelector("[data-pdf-preview]");
    const generic = form.querySelector("[data-generic-preview]");
    let objectUrl = null;

    function resetPreview() {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = null;
      [img, pdf, generic].forEach(function (el) { if (el) el.classList.add("d-none"); });
      if (box) box.classList.add("d-none");
      if (confirmBox) { confirmBox.checked = false; confirmBox.disabled = true; }
      if (submit) submit.disabled = true;
    }

    if (!input) return;
    input.addEventListener("change", function () {
      resetPreview();
      const file = input.files && input.files[0];
      if (!file) return;
      objectUrl = URL.createObjectURL(file);
      if (box) box.classList.remove("d-none");
      if (nameEl) nameEl.textContent = file.name + " (" + Math.ceil(file.size / 1024) + " KB)";
      if (file.type.indexOf("image/") === 0 && img) {
        img.src = objectUrl;
        img.classList.remove("d-none");
      } else if (file.type === "application/pdf" && pdf) {
        pdf.data = objectUrl;
        pdf.classList.remove("d-none");
      } else if (generic) {
        generic.classList.remove("d-none");
      }
      if (confirmBox) confirmBox.disabled = false;
    });

    if (confirmBox) {
      confirmBox.addEventListener("change", function () {
        if (submit) submit.disabled = !confirmBox.checked;
      });
    }

    form.addEventListener("submit", function (event) {
      if (!input.files || !input.files[0]) {
        event.preventDefault();
        input.focus();
        return;
      }
      if (confirmBox && !confirmBox.checked) {
        event.preventDefault();
        confirmBox.focus();
        return;
      }
      if (submit) {
        submit.disabled = true;
        submit.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>' + (submit.dataset.loadingText || 'Uploading...');
        submit.setAttribute("aria-label", submit.dataset.loadingText || "Uploading...");
      }
    });
  });
});

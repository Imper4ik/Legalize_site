document.addEventListener('DOMContentLoaded', function () {
    // Initialize all three date pickers
    flatpickr("#legal_basis_end_date_picker", { wrap: true, dateFormat: "d.m.Y", allowInput: true, clickOpens: false });
    flatpickr("#fingerprints_date_picker", { wrap: true, dateFormat: "d.m.Y", allowInput: true, clickOpens: false });
    flatpickr("#submission_date_picker", { wrap: true, dateFormat: "d.m.Y", allowInput: true, clickOpens: false });

    // Notes editor logic
    const mainEditor = document.getElementById('notes-editor');
    const hiddenInput = document.getElementById('id_notes_hidden');
    const form = mainEditor.closest('form');
    document.querySelector('.format-button[data-format="bold"]').addEventListener('click', function (e) { e.preventDefault(); document.execCommand('bold', false, null); mainEditor.focus(); });
    if (form) { form.addEventListener('submit', function () { if (hiddenInput && mainEditor) { hiddenInput.value = mainEditor.innerHTML; } }); }
  });

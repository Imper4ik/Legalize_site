document.addEventListener("DOMContentLoaded", function() {
        const wasPolYes = document.getElementById("wasPolYes");
        const wasPolNo = document.getElementById("wasPolNo");
        const prevStaysContainer = document.getElementById("previousStaysContainer");

        function togglePreviousStays() {
            if (wasPolYes.checked) {
                prevStaysContainer.style.display = "block";
            } else {
                prevStaysContainer.style.display = "none";
            }
        }
        wasPolYes.addEventListener("change", togglePreviousStays);
        wasPolNo.addEventListener("change", togglePreviousStays);
        togglePreviousStays();
    });

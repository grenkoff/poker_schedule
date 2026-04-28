// `Early bird type` is meaningful only when `Early bird` is checked.
// Disable the dropdown otherwise — but flip it back to enabled right
// before form submit so the FK value still rides along (the model field
// is non-nullable, so we always need a value to be posted).
(function () {
    "use strict";

    function init() {
        var checkbox = document.getElementById("id_early_bird");
        var typeSelect = document.getElementById("id_early_bird_type");
        if (!checkbox || !typeSelect) {
            return;
        }

        function sync() {
            typeSelect.disabled = !checkbox.checked;
        }
        checkbox.addEventListener("change", sync);
        sync();

        var form = checkbox.closest("form");
        if (form) {
            form.addEventListener("submit", function () {
                typeSelect.disabled = false;
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

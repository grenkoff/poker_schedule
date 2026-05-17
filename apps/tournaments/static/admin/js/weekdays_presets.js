/* Inject "All / Weekdays / Weekends" preset buttons below the weekday
 * checkbox group on the Tournament admin form. Pure UX sugar — the
 * checkboxes themselves are the source of truth that the form submits. */
(function () {
    "use strict";

    var PRESETS = [
        { label: "All", days: [0, 1, 2, 3, 4, 5, 6] },
        { label: "Weekdays", days: [0, 1, 2, 3, 4] },
        { label: "Weekends", days: [5, 6] },
    ];

    function init() {
        var row = document.querySelector(".field-weekdays");
        if (!row) return;
        var boxes = Array.prototype.slice.call(
            row.querySelectorAll('input[type="checkbox"]')
        );
        if (boxes.length !== 7) return;
        if (row.querySelector(".tnmt-weekday-presets")) return;

        var bar = document.createElement("div");
        bar.className = "tnmt-weekday-presets";
        bar.style.marginTop = "6px";
        bar.style.fontSize = "0.85em";

        var prefix = document.createElement("span");
        prefix.textContent = "Presets: ";
        prefix.style.color = "#666";
        bar.appendChild(prefix);

        PRESETS.forEach(function (preset, idx) {
            if (idx > 0) {
                var sep = document.createElement("span");
                sep.textContent = " | ";
                sep.style.color = "#bbb";
                bar.appendChild(sep);
            }
            var btn = document.createElement("a");
            btn.href = "#";
            btn.textContent = preset.label;
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                boxes.forEach(function (box, i) {
                    box.checked = preset.days.indexOf(i) !== -1;
                });
            });
            bar.appendChild(btn);
        });

        // Place the preset bar after the checkbox list inside the field row.
        var helpText = row.querySelector(".help");
        if (helpText && helpText.parentNode === row) {
            row.insertBefore(bar, helpText);
        } else {
            row.appendChild(bar);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

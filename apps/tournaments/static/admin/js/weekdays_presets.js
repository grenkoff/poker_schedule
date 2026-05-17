/* "Active weekdays" field UX on the Tournament admin form:
 *   - inject "All / Weekdays / Weekends" preset links
 *   - disable the 7 checkboxes (and the preset links) whenever
 *     Periodicity is unset or one-off — those tournaments don't get
 *     recurring children, so the mask is unused.
 *
 * The Periodicity widget tags each <option> with data-interval-seconds;
 * "0" means one-off. An empty value means "no selection yet" — also
 * disabled.
 */
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

        var presetLinks = renderPresets(row, boxes);
        var select = document.querySelector('select[data-tnmt-periodicity="1"]');
        if (!select) {
            // Form rendered without our custom widget — leave checkboxes
            // alone, the user can still interact with them.
            return;
        }

        function isRecurring() {
            var opt = select.options[select.selectedIndex];
            if (!opt) return false;
            var raw = opt.getAttribute("data-interval-seconds");
            if (raw === null || raw === "") return false;
            return parseInt(raw, 10) > 0;
        }

        function applyState() {
            var on = isRecurring();
            boxes.forEach(function (box) { box.disabled = !on; });
            presetLinks.forEach(function (a) {
                if (on) {
                    a.classList.remove("tnmt-disabled");
                    a.removeAttribute("aria-disabled");
                } else {
                    a.classList.add("tnmt-disabled");
                    a.setAttribute("aria-disabled", "true");
                }
            });
            row.classList.toggle("tnmt-weekdays-disabled", !on);
        }

        select.addEventListener("change", applyState);
        applyState();
    }

    function renderPresets(row, boxes) {
        if (row.querySelector(".tnmt-weekday-presets")) {
            return Array.prototype.slice.call(
                row.querySelectorAll(".tnmt-weekday-presets a")
            );
        }
        var bar = document.createElement("div");
        bar.className = "tnmt-weekday-presets";
        bar.style.marginTop = "6px";
        bar.style.fontSize = "0.85em";

        var prefix = document.createElement("span");
        prefix.textContent = "Presets: ";
        prefix.style.color = "#666";
        bar.appendChild(prefix);

        var links = [];
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
                if (btn.classList.contains("tnmt-disabled")) return;
                boxes.forEach(function (box, i) {
                    box.checked = preset.days.indexOf(i) !== -1;
                });
            });
            bar.appendChild(btn);
            links.push(btn);
        });

        var helpText = row.querySelector(".help");
        if (helpText && helpText.parentNode === row) {
            row.insertBefore(bar, helpText);
        } else {
            row.appendChild(bar);
        }
        return links;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

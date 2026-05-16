/* Renders <time data-local-dt> in the user's timezone, embeds a UTC-offset
 * picker into th[data-tz-picker], and appends a "(UTC+X)" label to other
 * tz-aware headers. Offset list is fixed (UTC-12…UTC+14) so it stays a
 * usable size; "Auto" follows the browser's reported offset.
 */
(function () {
    "use strict";

    var STORAGE_KEY = "tz-offset-minutes";

    function pad(n) { return n < 10 ? "0" + n : "" + n; }

    function browserOffsetMinutes() {
        // getTimezoneOffset returns minutes WEST of UTC, so negate.
        return -new Date().getTimezoneOffset();
    }

    function chosenOffset() {
        var raw = localStorage.getItem(STORAGE_KEY);
        if (raw === null || raw === "") return null;
        var n = parseInt(raw, 10);
        return isNaN(n) ? null : n;
    }

    function nearestOffsetMinutes(actual) {
        var rounded = Math.round(actual / 60) * 60;
        if (rounded < -720) rounded = -720;
        if (rounded > 840) rounded = 840;
        return rounded;
    }

    function effectiveOffset() {
        var c = chosenOffset();
        return c === null ? nearestOffsetMinutes(browserOffsetMinutes()) : c;
    }

    // Whole-hour offsets paired with a recognizable city. Keeps the
    // picker short while giving users a familiar reference point.
    var TZ_OFFSETS = [
        [-720, "Baker Island"],
        [-660, "Pago Pago"],
        [-600, "Honolulu"],
        [-540, "Anchorage"],
        [-480, "Los Angeles"],
        [-420, "Denver"],
        [-360, "Mexico City"],
        [-300, "New York"],
        [-240, "Santiago"],
        [-180, "São Paulo"],
        [-120, "South Georgia"],
        [-60, "Azores"],
        [0, "London"],
        [60, "Berlin"],
        [120, "Athens"],
        [180, "Moscow"],
        [240, "Dubai"],
        [300, "Almaty"],
        [360, "Dhaka"],
        [420, "Bangkok"],
        [480, "Singapore"],
        [540, "Tokyo"],
        [600, "Sydney"],
        [660, "Nouméa"],
        [720, "Auckland"],
        [780, "Apia"],
        [840, "Kiritimati"],
    ];

    function offsetLabel(minutes) {
        var sign = minutes >= 0 ? "+" : "-";
        var abs = Math.abs(minutes);
        var h = Math.floor(abs / 60);
        var m = abs % 60;
        return m === 0
            ? "UTC" + sign + h
            : "UTC" + sign + h + ":" + pad(m);
    }

    function formatInOffset(date, offsetMinutes) {
        var shifted = new Date(date.getTime() + offsetMinutes * 60 * 1000);
        return pad(shifted.getUTCDate()) + "." + pad(shifted.getUTCMonth() + 1) + "." + shifted.getUTCFullYear() +
            " " + pad(shifted.getUTCHours()) + ":" + pad(shifted.getUTCMinutes());
    }

    function localizeCells(root, offset) {
        var nodes = (root || document).querySelectorAll("time[data-local-dt]");
        nodes.forEach(function (el) {
            var iso = el.getAttribute("datetime");
            if (!iso) return;
            var d = new Date(iso);
            if (isNaN(d.getTime())) return;
            el.textContent = formatInOffset(d, offset);
        });
    }

    function tzAwareHeaders(table) {
        var heads = Array.from(table.querySelectorAll("thead th"));
        var explicit = heads.filter(function (th) { return th.hasAttribute("data-tz-col"); });
        if (explicit.length) return explicit;
        var detected = [];
        heads.forEach(function (th, idx) {
            var hasTime = table.querySelector("tbody tr td:nth-child(" + (idx + 1) + ") time[data-local-dt]");
            if (hasTime) detected.push(th);
        });
        return detected;
    }

    function clearAnnotation(th) {
        Array.from(th.querySelectorAll(".tz-anno")).forEach(function (n) { n.remove(); });
    }

    function ensurePicker(th) {
        var sel = th.querySelector("select.tz-picker");
        if (!sel) {
            sel = document.createElement("select");
            sel.className = "tz-picker";
            // Stop click propagation so a click in the header cell doesn't
            // also trigger sort. Change events are handled via delegation
            // on document.body (so cloned <select>s work too).
            sel.addEventListener("click", function (e) { e.stopPropagation(); });
            var br = document.createElement("br");
            br.className = "tz-picker-br";
            th.appendChild(br);
            th.appendChild(sel);
            TZ_OFFSETS.forEach(function (entry) {
                var opt = document.createElement("option");
                opt.value = String(entry[0]);
                opt.textContent = offsetLabel(entry[0]) + " " + entry[1];
                sel.appendChild(opt);
            });
        }
        sel.value = String(effectiveOffset());
    }

    function applyAll() {
        var offset = effectiveOffset();
        document.querySelectorAll("table").forEach(function (table) {
            localizeCells(table, offset);
            tzAwareHeaders(table).forEach(function (th) {
                clearAnnotation(th);
                ensurePicker(th);
            });
        });
        // Keep all picker <select>s (including any cloned into the sticky
        // thead ghost) in sync with the current chosen offset.
        document.querySelectorAll("select.tz-picker").forEach(function (s) {
            s.value = String(offset);
        });
    }

    function init() {
        applyAll();
        if (document.body) {
            document.body.addEventListener("htmx:afterSwap", function () { applyAll(); });
            // Event delegation: catch change on any picker (original or clone).
            document.body.addEventListener("change", function (e) {
                if (e.target && e.target.classList && e.target.classList.contains("tz-picker")) {
                    localStorage.setItem(STORAGE_KEY, e.target.value);
                    applyAll();
                }
            });
        }
        // sticky_thead clones the original thead — its <select> ends up at
        // selectedIndex 0. After it rebuilds, re-run applyAll to push the
        // effective offset into the cloned picker(s).
        window.addEventListener("sticky-thead-rebuilt", applyAll);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

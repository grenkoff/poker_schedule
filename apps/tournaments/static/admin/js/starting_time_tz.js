/* Timezone picker in the changelist "Starting time" column header.
 *
 * Each cell carries the underlying UTC instant(s) in
 * `<span data-tz-times="[iso,...]" data-tz-kind="time|datetime">`. This
 * script injects a city/offset <select> into the column header and rewrites
 * every cell into the chosen offset:
 *   - kind="time"      → just the time(s) of day (HH:MM, deduped + sorted),
 *   - kind="datetime"  → full date + time (one-off tournaments).
 * The chosen offset is persisted under the same localStorage key as the
 * public list's picker, so "my timezone" stays consistent across the app.
 */
(function () {
    "use strict";

    var STORAGE_KEY = "tz-offset-minutes";

    // Whole-hour offsets + a recognizable city — mirrors localize_times.js.
    var TZ_OFFSETS = [
        [-720, "Baker Island"], [-660, "Pago Pago"], [-600, "Honolulu"],
        [-540, "Anchorage"], [-480, "Los Angeles"], [-420, "Denver"],
        [-360, "Mexico City"], [-300, "New York"], [-240, "Santiago"],
        [-180, "São Paulo"], [-120, "South Georgia"], [-60, "Azores"],
        [0, "London"], [60, "Berlin"], [120, "Athens"], [180, "Moscow"],
        [240, "Dubai"], [300, "Almaty"], [360, "Dhaka"], [420, "Bangkok"],
        [480, "Singapore"], [540, "Tokyo"], [600, "Sydney"], [660, "Nouméa"],
        [720, "Auckland"], [780, "Apia"], [840, "Kiritimati"],
    ];

    function pad(n) { return n < 10 ? "0" + n : "" + n; }

    function browserOffsetMinutes() { return -new Date().getTimezoneOffset(); }

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

    function offsetLabel(minutes) {
        var sign = minutes >= 0 ? "+" : "-";
        var abs = Math.abs(minutes);
        var h = Math.floor(abs / 60);
        var m = abs % 60;
        return m === 0 ? "UTC" + sign + h : "UTC" + sign + h + ":" + pad(m);
    }

    function shift(iso, offMin) {
        var d = new Date(iso);
        return new Date(d.getTime() + offMin * 60 * 1000);
    }

    function fmtTime(iso, offMin) {
        var s = shift(iso, offMin);
        return pad(s.getUTCHours()) + ":" + pad(s.getUTCMinutes());
    }

    function fmtDateTime(iso, offMin) {
        var s = shift(iso, offMin);
        return pad(s.getUTCDate()) + "." + pad(s.getUTCMonth() + 1) + "." + s.getUTCFullYear()
            + " " + pad(s.getUTCHours()) + ":" + pad(s.getUTCMinutes());
    }

    function applyCells(off) {
        document.querySelectorAll("#result_list span[data-tz-times]").forEach(function (span) {
            var times;
            try { times = JSON.parse(span.getAttribute("data-tz-times")); } catch (e) { return; }
            if (!times || !times.length) return;
            if (span.getAttribute("data-tz-kind") === "datetime") {
                span.textContent = fmtDateTime(times[0], off);
            } else {
                var hhmm = times.map(function (iso) { return fmtTime(iso, off); });
                hhmm = Array.from(new Set(hhmm)).sort();
                span.textContent = hhmm.join(", ");
            }
        });
    }

    function injectPicker() {
        var th = document.querySelector("#result_list thead th.column-starting_time_display");
        if (!th || th.querySelector("select.tnmt-tz-picker")) return;
        var sel = document.createElement("select");
        sel.className = "tnmt-tz-picker";
        var off = effectiveOffset();
        TZ_OFFSETS.forEach(function (e) {
            var o = document.createElement("option");
            o.value = String(e[0]);
            o.textContent = offsetLabel(e[0]) + " " + e[1];
            if (e[0] === off) o.selected = true;
            sel.appendChild(o);
        });
        sel.addEventListener("click", function (e) { e.stopPropagation(); });
        sel.addEventListener("change", function () {
            localStorage.setItem(STORAGE_KEY, sel.value);
            applyCells(parseInt(sel.value, 10));
        });
        th.appendChild(document.createElement("br"));
        th.appendChild(sel);
    }

    function init() {
        if (!document.getElementById("result_list")) return;
        injectPicker();
        applyCells(effectiveOffset());
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());

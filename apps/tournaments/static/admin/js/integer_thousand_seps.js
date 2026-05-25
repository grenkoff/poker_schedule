/* Show integer inputs with thousand separators (e.g. "300,000,000").
 *
 * Browsers reject commas in `<input type="number">`, so this script
 * converts every targeted integer input to `<input type="text"
 * inputmode="numeric">` on page load. The visible value is reformatted
 * on every keystroke (caret position preserved) and the form's submit
 * handler strips commas just before serialization so the server still
 * receives a plain integer.
 *
 * Targets: every `<input type="number">` that is NOT a decimal input
 * (`inputmode="decimal"`). Readonly integer inputs are converted too —
 * the `input` event fires when other scripts (e.g. blind-level
 * autonumber) write to them via dispatched events, keeping the
 * displayed value formatted.
 *
 * Server-side validators (MinValueValidator / MaxValueValidator on the
 * model) remain authoritative; the HTML5 `min`/`max`/`step` attrs no
 * longer constrain typing once the input is `type="text"`.
 */
(function () {
    "use strict";

    var DATA_ATTR = "data-int-format";

    function isPlainNumberInput(el) {
        return (
            el instanceof HTMLInputElement &&
            el.type === "number" &&
            el.getAttribute("inputmode") !== "decimal"
        );
    }

    function digits(s) {
        return (s || "").replace(/\D/g, "");
    }

    function withCommas(d) {
        return d.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    }

    function convertToText(el) {
        el.type = "text";
        el.setAttribute("inputmode", "numeric");
        el.setAttribute(DATA_ATTR, "1");
        var d = digits(el.value);
        el.value = d ? withCommas(d) : "";
    }

    function reformat(el) {
        var caret = el.selectionStart;
        var digitsBefore = caret == null ? null : digits(el.value.slice(0, caret)).length;
        var d = digits(el.value);
        var formatted = d ? withCommas(d) : "";
        if (formatted === el.value) return;
        el.value = formatted;
        if (digitsBefore == null) return;
        // Restore caret: walk forward in the formatted string until
        // we've passed the same number of digit characters that were
        // to the left of the caret before reformatting.
        var pos = 0, seen = 0;
        while (pos < formatted.length && seen < digitsBefore) {
            if (/\d/.test(formatted.charAt(pos))) seen++;
            pos++;
        }
        try {
            el.setSelectionRange(pos, pos);
        } catch (e) {
            /* not focusable (e.g. readonly) — ignore */
        }
    }

    function convertAll() {
        document
            .querySelectorAll('input[type="number"]')
            .forEach(function (el) {
                if (isPlainNumberInput(el)) convertToText(el);
            });
    }

    function bindForms() {
        document.querySelectorAll("form").forEach(function (form) {
            if (form.dataset.intFormBound) return;
            form.dataset.intFormBound = "1";
            form.addEventListener("submit", function () {
                form
                    .querySelectorAll('input[' + DATA_ATTR + '="1"]')
                    .forEach(function (inp) {
                        inp.value = digits(inp.value);
                    });
            });
        });
    }

    function init() {
        convertAll();
        bindForms();
        document.addEventListener("input", function (e) {
            var el = e.target;
            if (el && el.getAttribute && el.getAttribute(DATA_ATTR) === "1") {
                reformat(el);
            }
        });
        // Newly-added inline rows arrive as type="number" inputs; convert
        // and bind them after Django finishes inserting the row.
        document.addEventListener("formset:added", function () {
            convertAll();
            bindForms();
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

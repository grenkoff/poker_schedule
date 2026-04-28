// `Buy-in with rake` is always derived from `Buy-in without rake + Rake`
// and rendered read-only. This script keeps the visible value in sync as
// the editor types into the other two fields. The server-side `clean()`
// is still authoritative.
(function () {
    "use strict";

    function init() {
        var withoutRake = document.getElementById("id_buy_in_without_rake");
        var rake = document.getElementById("id_rake");
        var total = document.getElementById("id_buy_in_total");
        if (!withoutRake || !rake || !total) {
            return;
        }

        // For every decimal input on this form, restrict typing to digits
        // and at most one dot. Comma is rewritten to dot so editors with
        // EU/RU keyboard habits can type "4,60" and have it land as "4.60".
        // Paste is sanitized the same way.
        var CONTROL_KEYS = [
            "Backspace", "Delete", "Tab", "Enter", "Escape",
            "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
            "Home", "End",
        ];

        function hasDotOutsideSelection(input) {
            var start = input.selectionStart || 0;
            var end = input.selectionEnd || 0;
            var rest = input.value.slice(0, start) + input.value.slice(end);
            return rest.indexOf(".") !== -1;
        }

        function insertAtCaret(input, text) {
            var start = input.selectionStart || 0;
            var end = input.selectionEnd || 0;
            var value = input.value;
            input.value = value.slice(0, start) + text + value.slice(end);
            input.setSelectionRange(start + text.length, start + text.length);
            input.dispatchEvent(new Event("input", { bubbles: true }));
        }

        function wouldExceedTwoDecimals(input, insertText) {
            var start = input.selectionStart || 0;
            var end = input.selectionEnd || 0;
            var next = input.value.slice(0, start) + insertText + input.value.slice(end);
            var dot = next.indexOf(".");
            return dot !== -1 && next.length - dot - 1 > 2;
        }

        function clampToTwoDecimals(text) {
            var dot = text.indexOf(".");
            if (dot === -1) {
                return text;
            }
            return text.slice(0, dot + 1) + text.slice(dot + 1, dot + 3);
        }

        document.querySelectorAll('input[inputmode="decimal"]').forEach(function (input) {
            input.addEventListener("keydown", function (e) {
                // Modifier combos (Ctrl+A/C/V/X, ⌘+...) pass through.
                if (e.ctrlKey || e.metaKey || e.altKey) {
                    return;
                }
                if (CONTROL_KEYS.indexOf(e.key) !== -1) {
                    return;
                }
                if (e.key === "," || e.key === "Decimal") {
                    e.preventDefault();
                    if (hasDotOutsideSelection(input)) {
                        return;
                    }
                    insertAtCaret(input, ".");
                    return;
                }
                if (e.key === ".") {
                    if (hasDotOutsideSelection(input)) {
                        e.preventDefault();
                    }
                    return;
                }
                if (e.key.length === 1 && !/^\d$/.test(e.key)) {
                    e.preventDefault();
                    return;
                }
                if (/^\d$/.test(e.key) && wouldExceedTwoDecimals(input, e.key)) {
                    e.preventDefault();
                }
            });

            input.addEventListener("paste", function (e) {
                e.preventDefault();
                var clip = e.clipboardData || window.clipboardData;
                var text = clip ? clip.getData("text") : "";
                text = text.replace(/,/g, ".").replace(/[^0-9.]/g, "");
                var dot = text.indexOf(".");
                if (dot !== -1) {
                    text = text.slice(0, dot + 1) + text.slice(dot + 1).replace(/\./g, "");
                }
                if (hasDotOutsideSelection(input)) {
                    text = text.replace(/\./g, "");
                }
                if (!text) {
                    return;
                }
                var start = input.selectionStart || 0;
                var end = input.selectionEnd || 0;
                var combined = clampToTwoDecimals(
                    input.value.slice(0, start) + text + input.value.slice(end)
                );
                input.value = combined;
                var caret = Math.min(start + text.length, combined.length);
                input.setSelectionRange(caret, caret);
                input.dispatchEvent(new Event("input", { bubbles: true }));
            });
        });

        function parse(input) {
            var raw = (input.value || "").trim().replace(",", ".");
            if (raw === "") {
                return null;
            }
            var n = Number(raw);
            return Number.isFinite(n) ? n : null;
        }

        function format(n) {
            return (Math.round(n * 100) / 100).toFixed(2);
        }

        var rakePercent = document.getElementById("id_rake_percent");

        function recompute() {
            var w = parse(withoutRake);
            var r = parse(rake);
            if (w === null || r === null) {
                total.value = "";
                if (rakePercent) {
                    rakePercent.value = "";
                }
                return;
            }
            var sum = w + r;
            if (sum < 0) {
                total.value = "";
                if (rakePercent) {
                    rakePercent.value = "";
                }
                return;
            }
            total.value = format(sum);
            if (rakePercent) {
                rakePercent.value = sum > 0 ? format((r / sum) * 100) : "";
            }
        }

        [withoutRake, rake].forEach(function (f) {
            f.addEventListener("input", recompute);
            f.addEventListener("blur", function () {
                var n = parse(f);
                if (n !== null) {
                    f.value = format(n);
                }
                recompute();
            });
        });

        recompute();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

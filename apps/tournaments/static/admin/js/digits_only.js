// On the Tournament admin page, every `<input type="number">` is an
// integer field (decimal fields use TextInput with inputmode="decimal").
// Restrict typing to digits + control keys so editors can't even type a
// stray dot, comma, letter or sign character. Paste is sanitized too.
//
// We use document-level delegation so dynamically added inline rows
// (e.g. extra Blind levels) inherit the same behavior.
(function () {
    "use strict";

    var CONTROL_KEYS = [
        "Backspace", "Delete", "Tab", "Enter", "Escape",
        "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
        "Home", "End",
    ];

    function isIntegerInput(target) {
        return (
            target instanceof HTMLInputElement &&
            target.type === "number" &&
            target.getAttribute("inputmode") !== "decimal"
        );
    }

    document.addEventListener("keydown", function (e) {
        if (!isIntegerInput(e.target)) {
            return;
        }
        if (e.ctrlKey || e.metaKey || e.altKey) {
            return;
        }
        if (CONTROL_KEYS.indexOf(e.key) !== -1) {
            return;
        }
        if (e.key.length === 1 && !/^\d$/.test(e.key)) {
            e.preventDefault();
        }
    });

    document.addEventListener("paste", function (e) {
        if (!isIntegerInput(e.target)) {
            return;
        }
        var clip = e.clipboardData || window.clipboardData;
        var text = clip ? clip.getData("text") : "";
        var digits = text.replace(/\D/g, "");
        if (digits === text) {
            return;
        }
        e.preventDefault();
        if (!digits) {
            return;
        }
        var input = e.target;
        var start = input.selectionStart || 0;
        var end = input.selectionEnd || 0;
        var value = input.value;
        input.value = value.slice(0, start) + digits + value.slice(end);
        input.setSelectionRange(start + digits.length, start + digits.length);
        input.dispatchEvent(new Event("input", { bubbles: true }));
    });
})();

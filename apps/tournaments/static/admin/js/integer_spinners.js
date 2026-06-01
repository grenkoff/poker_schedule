/* Custom up/down spinners for integer inputs.
 *
 * The native `<input type="number">` spin buttons disappear once
 * integer_thousand_seps.js rewrites those inputs to `type="text"`
 * (required so the value can carry thousand separators). This script
 * re-adds equivalent ▲/▼ buttons that increment / decrement the value
 * and dispatch `input` + `change`, so every dependent script stays in
 * sync — the thousand-separator reformatter, the blind-level
 * small-blind derivation, the late-reg duration recompute, etc.
 *
 * Targets every input that integer_thousand_seps marked with
 * `data-int-format="1"`, except readonly/disabled ones (e.g. the derived
 * small-blind column). Bounds come from the surviving `min`/`max`/`step`
 * attributes; the server-side validators remain authoritative.
 */
(function () {
    "use strict";

    function digits(s) {
        return (s || "").replace(/\D/g, "");
    }

    function intAttr(el, name) {
        var raw = el.getAttribute(name);
        if (raw === null || raw === "") return null;
        var n = parseInt(raw, 10);
        return isNaN(n) ? null : n;
    }

    function stepFor(el) {
        var s = intAttr(el, "step");
        return s && s > 0 ? s : 1;
    }

    function clamp(el, n) {
        var min = intAttr(el, "min");
        var max = intAttr(el, "max");
        if (min !== null && n < min) n = min;
        if (max !== null && n > max) n = max;
        if (n < 0) n = 0;
        return n;
    }

    function bump(el, dir) {
        if (el.readOnly || el.disabled) return;
        var cur = parseInt(digits(el.value), 10);
        if (isNaN(cur)) cur = 0;
        el.value = String(clamp(el, cur + dir * stepFor(el)));
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function makeBtn(cls, glyph, el, dir) {
        var b = document.createElement("button");
        b.type = "button";
        b.tabIndex = -1;
        b.className = "tnmt-spin-btn " + cls;
        b.setAttribute("aria-hidden", "true");
        b.textContent = glyph;
        b.addEventListener("click", function (e) {
            e.preventDefault();
            bump(el, dir);
        });
        return b;
    }

    function wrap(el) {
        if (el.dataset.intSpin === "1") return;
        if (el.readOnly || el.disabled) return;
        el.dataset.intSpin = "1";

        var w = document.createElement("span");
        w.className = "tnmt-spin-wrap";
        el.parentNode.insertBefore(w, el);
        w.appendChild(el);

        var btns = document.createElement("span");
        btns.className = "tnmt-spin-btns";
        btns.appendChild(makeBtn("tnmt-spin-up", "▲", el, +1));
        btns.appendChild(makeBtn("tnmt-spin-down", "▼", el, -1));
        w.appendChild(btns);
    }

    function wrapAll() {
        document
            .querySelectorAll('input[data-int-format="1"]')
            .forEach(wrap);
    }

    function init() {
        wrapAll();
        // New inline rows are converted by integer_thousand_seps on the
        // same event; defer a tick so `data-int-format` is already set.
        document.addEventListener("formset:added", function () {
            setTimeout(wrapAll, 0);
        });
    }

    // Run after integer_thousand_seps.js has converted the inputs (it is
    // loaded before this file and also defers to DOMContentLoaded).
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            setTimeout(init, 0);
        });
    } else {
        setTimeout(init, 0);
    }
})();

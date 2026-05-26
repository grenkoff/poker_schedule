/* Apply a saved BlindStructureTemplate to the Tournament inline.
 *
 * Listens for changes on the `apply_template` Select (tagged with
 * `data-tnmt-template`). The selected <option> carries a JSON-encoded
 * `data-levels` attribute that is the full list of rows for that
 * template — embedded server-side by `BlindStructureTemplateWidget`.
 *
 * Strategy: REUSE the existing formset rows in order (so saved-row PKs
 * are kept and Django performs UPDATEs rather than DELETE-INSERT in
 * the common edit case); add new rows only when the template has more
 * levels than the inline currently shows; mark excess saved rows for
 * deletion. Plays nicely with `blind_levels_autonumber.js`.
 */
(function () {
    "use strict";

    var FORMSET_PREFIX = "blind_levels";
    var ROW_LEVEL_RE = /^blind_levels-(\d+)-level$/;

    function rowIndices() {
        var idxs = [];
        Array.prototype.forEach.call(
            document.querySelectorAll(
                'input[name^="' + FORMSET_PREFIX + '-"][name$="-level"]'
            ),
            function (inp) {
                var m = inp.name.match(ROW_LEVEL_RE);
                if (m) idxs.push(parseInt(m[1], 10));
            }
        );
        idxs.sort(function (a, b) { return a - b; });
        return idxs;
    }

    function field(idx, name) {
        return document.getElementById(
            "id_" + FORMSET_PREFIX + "-" + idx + "-" + name
        );
    }

    function rowElement(idx) {
        // Walk up from one of the row's inputs to the enclosing <tr>.
        // Used to hide excess rows so the inline visually matches the
        // template's level count.
        var anyInput = field(idx, "level");
        var el = anyInput;
        while (el && el.tagName !== "TR") el = el.parentNode;
        return el;
    }

    function setVal(input, value) {
        if (!input) return;
        input.value = value === null || value === undefined ? "" : String(value);
        // Fire `input` so integer_thousand_seps.js reformats with
        // commas (and any other listeners observe the new value).
        input.dispatchEvent(new Event("input", { bubbles: true }));
    }

    function dispatch(input, evt) {
        if (!input) return;
        input.dispatchEvent(new Event(evt, { bubbles: true }));
    }

    function clickAddRow() {
        // Django admin renders the tabular inline's add link as a single
        // <a> inside <tr class="add-row">. Match it within the inline's
        // own scope so a second inline on the page (none today, but
        // robustness costs nothing) doesn't get clicked instead.
        var scope = document.getElementById(FORMSET_PREFIX + "-group");
        var link = (scope || document).querySelector("tr.add-row a");
        if (!link) {
            console.warn("[blind_template_apply] add-row link not found");
            return false;
        }
        link.click();
        return true;
    }

    function applyLevels(levels) {
        var have = rowIndices();
        var need = levels.length;

        // Add missing rows by clicking the "Add another Blind level" link.
        // Django inserts each row synchronously, so a tight loop is safe.
        for (var i = have.length; i < need; i++) {
            if (!clickAddRow()) break;
        }

        var rows = rowIndices();
        for (var j = 0; j < rows.length; j++) {
            var idx = rows[j];
            var del = field(idx, "DELETE");
            var row = rowElement(idx);
            if (j < need) {
                var spec = levels[j];
                // spec = [level, small_blind, big_blind, ante]
                setVal(field(idx, "level"), spec[0]);
                setVal(field(idx, "small_blind"), spec[1]);
                setVal(field(idx, "big_blind"), spec[2]);
                setVal(field(idx, "ante"), spec[3] ? spec[3] : "");
                if (del) del.checked = false;
                // Restore visibility in case this row was previously
                // hidden because a smaller template was loaded first.
                if (row) row.style.display = "";
                // Let autonumber's derive-small-blind handler observe the
                // change so the row stays internally consistent for
                // subsequent user edits.
                dispatch(field(idx, "big_blind"), "change");
            } else {
                // Excess existing row beyond the template's length. Saved
                // rows (those with a populated -id hidden input) get the
                // DELETE flag so Django removes them on submit; unsaved
                // rows just have their values cleared. Either way the
                // row is visually hidden so the inline only shows what
                // the chosen template defines.
                var idInput = field(idx, "id");
                if (idInput && idInput.value && del) {
                    del.checked = true;
                } else {
                    setVal(field(idx, "level"), "");
                    setVal(field(idx, "small_blind"), "");
                    setVal(field(idx, "big_blind"), "");
                    setVal(field(idx, "ante"), "");
                }
                if (row) row.style.display = "none";
            }
        }
    }

    function onTemplateChange(e) {
        var sel = e.target;
        if (!sel || !sel.matches || !sel.matches("select[data-tnmt-template]")) return;
        var opt = sel.options[sel.selectedIndex];
        if (!opt) return;
        var raw = opt.getAttribute("data-levels");
        if (!raw) return;
        var levels;
        try {
            levels = JSON.parse(raw);
        } catch (err) {
            console.warn("[blind_template_apply] could not parse data-levels", err);
            return;
        }
        if (!Array.isArray(levels) || levels.length === 0) return;
        console.info(
            "[blind_template_apply] applying template '" + opt.text +
            "' (" + levels.length + " rows) to the BLIND LEVELS inline"
        );
        applyLevels(levels);
    }

    function init() {
        document.addEventListener("change", onTemplateChange);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

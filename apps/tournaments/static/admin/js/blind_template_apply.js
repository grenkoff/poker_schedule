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

    function setVal(input, value) {
        if (!input) return;
        input.value = value === null || value === undefined ? "" : String(value);
    }

    function dispatch(input, evt) {
        if (!input) return;
        input.dispatchEvent(new Event(evt, { bubbles: true }));
    }

    function clickAddRow() {
        // Django admin's TabularInline renders the add link as the only
        // <a> inside <tr.add-row> (or <a class="addlink">). Either selector
        // resolves to a single anchor for our `blind_levels` inline.
        var link =
            document.querySelector(
                '[id^="blind_levels-"] tr.add-row a, ' +
                '.dynamic-form a.add-row, ' +
                '.inline-related a.addlink'
            ) ||
            document.querySelector("tr.add-row a");
        if (!link) return false;
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
            if (j < need) {
                var spec = levels[j];
                // spec = [level, small_blind, big_blind, ante]
                setVal(field(idx, "level"), spec[0]);
                setVal(field(idx, "small_blind"), spec[1]);
                setVal(field(idx, "big_blind"), spec[2]);
                setVal(field(idx, "ante"), spec[3] ? spec[3] : "");
                if (del) del.checked = false;
                // Let autonumber's derive-small-blind handler observe the
                // change so the row stays internally consistent for
                // subsequent user edits.
                dispatch(field(idx, "big_blind"), "change");
            } else {
                // Excess existing row beyond the template's length. Saved
                // rows (those with a populated -id hidden input) get the
                // DELETE flag; unsaved rows just have their values cleared.
                var idInput = field(idx, "id");
                if (idInput && idInput.value && del) {
                    del.checked = true;
                } else {
                    setVal(field(idx, "level"), "");
                    setVal(field(idx, "small_blind"), "");
                    setVal(field(idx, "big_blind"), "");
                    setVal(field(idx, "ante"), "");
                }
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
            return;
        }
        if (!Array.isArray(levels) || levels.length === 0) return;
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

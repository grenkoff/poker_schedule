/* BlindStructure inline — auto-number the `level` column.
 *
 * - Pre-fill the first (empty) row with `level = 1`.
 * - On each new row added via "Добавить ещё один Blind level", set
 *   `level` to (max existing non-deleted level) + 1.
 * - Never overwrite an existing value (so editing a saved tournament
 *   keeps the user's numbering intact).
 */
(function () {
    "use strict";

    var FORMSET_PREFIX = "blind_levels";

    var ROW_LEVEL_RE = /^blind_levels-(\d+)-level$/;

    function rowLevelInputs() {
        return Array.prototype.filter.call(
            document.querySelectorAll(
                'input[name^="' + FORMSET_PREFIX + '-"][name$="-level"]'
            ),
            function (inp) {
                // Skip the empty-form template (`-__prefix__-`).
                return ROW_LEVEL_RE.test(inp.name);
            }
        );
    }

    function rowIsDeleted(input) {
        var m = input.name.match(ROW_LEVEL_RE);
        if (!m) return false;
        var del = document.getElementById(
            "id_" + FORMSET_PREFIX + "-" + m[1] + "-DELETE"
        );
        return del && del.checked;
    }

    function maxExistingLevel() {
        var max = 0;
        rowLevelInputs().forEach(function (inp) {
            if (rowIsDeleted(inp)) return;
            var v = parseInt(inp.value, 10);
            if (!isNaN(v) && v > max) max = v;
        });
        return max;
    }

    function initFirstRow() {
        var inputs = rowLevelInputs();
        if (inputs.length === 0) return;
        var first = inputs[0];
        if (!first.value) first.value = "1";
    }

    function onRowAdded() {
        // Don't trust `e.target` (varies across Django versions). Find
        // the freshly-added row by scanning for the only level input
        // that is still blank, then assign it max+1.
        var inputs = rowLevelInputs();
        var blank = null;
        inputs.forEach(function (inp) {
            if (!rowIsDeleted(inp) && !inp.value) blank = inp;
        });
        if (!blank) return;
        blank.value = String(maxExistingLevel() + 1);
    }

    /* ----- big_blind / small_blind derivation ----------------------- */

    function rowIndexFromName(name) {
        var m = name.match(/^blind_levels-(\d+)-/);
        return m ? m[1] : null;
    }

    function siblingInput(input, field) {
        var idx = rowIndexFromName(input.name);
        if (idx === null) return null;
        return document.getElementById("id_blind_levels-" + idx + "-" + field);
    }

    function recomputeSmallBlindFor(bigInput) {
        var sb = siblingInput(bigInput, "small_blind");
        if (!sb) return;
        var v = parseInt(bigInput.value, 10);
        sb.value = isNaN(v) ? "" : String(Math.floor(v / 2));
    }

    function recomputeFirstRowBigBlind() {
        var stackInp = document.getElementById("id_starting_stack");
        var bbInp = document.getElementById("id_starting_stack_bb");
        if (!stackInp || !bbInp) return;
        var stack = parseInt(stackInp.value, 10);
        var bb = parseInt(bbInp.value, 10);
        var first = document.getElementById("id_blind_levels-0-big_blind");
        if (!first) return;
        if (isNaN(stack) || isNaN(bb) || bb <= 0) {
            first.value = "";
        } else {
            first.value = String(Math.floor(stack / bb));
        }
        recomputeSmallBlindFor(first);
    }

    function markFirstRowBigBlindReadonly() {
        var first = document.getElementById("id_blind_levels-0-big_blind");
        if (!first) return;
        first.readOnly = true;
        first.style.backgroundColor = "#f0f0f0";
        first.style.cursor = "not-allowed";
        first.tabIndex = -1;
    }

    function bindBigBlindEdits() {
        // Event delegation: any user edit to a big_blind cell propagates
        // to that row's small_blind. Works for dynamically-added rows.
        ["input", "change"].forEach(function (evt) {
            document.addEventListener(evt, function (e) {
                var t = e.target;
                if (!t || !t.matches) return;
                if (
                    t.matches('input[name^="blind_levels-"][name$="-big_blind"]')
                ) {
                    recomputeSmallBlindFor(t);
                }
            });
        });
    }

    function bindStartingStackToFirstRow() {
        ["id_starting_stack", "id_starting_stack_bb"].forEach(function (id) {
            var inp = document.getElementById(id);
            if (!inp) return;
            ["input", "change", "blur"].forEach(function (evt) {
                inp.addEventListener(evt, recomputeFirstRowBigBlind);
            });
        });
    }

    function init() {
        initFirstRow();
        document.addEventListener("formset:added", onRowAdded);
        markFirstRowBigBlindReadonly();
        bindBigBlindEdits();
        bindStartingStackToFirstRow();
        // First-pass recompute (covers fresh add-form and existing rows
        // on edit-form alike — overwrites first-row values with the
        // derived figure).
        recomputeFirstRowBigBlind();
        // Ensure each existing row's small_blind is in sync with its
        // big_blind on edit-form load.
        document
            .querySelectorAll('input[name^="blind_levels-"][name$="-big_blind"]')
            .forEach(recomputeSmallBlindFor);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

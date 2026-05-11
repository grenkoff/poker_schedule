/* Public tournament list — per-user column visibility and order.
 *
 * Mirrors the admin changelist UX (modal with drag-and-drop + checkboxes,
 * sticky first column + sticky header) but uses a separate localStorage
 * key so prefs are independent from the admin's.
 */
(function () {
    "use strict";

    var STORAGE_KEY = "tnmt-changelist-cols:public-tournament";

    // Label of the column that is always first, non-movable, non-hideable.
    // Captured from the DOM before any reordering.
    var pinnedLabel = null;

    function $(sel, root) { return (root || document).querySelector(sel); }
    function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

    function getTable() {
        return document.querySelector("table[data-public-columns]");
    }

    function headerCells(table) {
        return $$("thead th", table);
    }

    function columnLabel(th) {
        return (th.textContent || "").replace(/\s+/g, " ").trim()
            .replace(/\s*[▲▼]$/, "").trim();
    }

    function allLabels(table) {
        return headerCells(table).map(columnLabel);
    }

    // ---- prefs: array of {label, visible} in desired display order ------

    function loadPrefs(table) {
        try {
            var raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
            if (Array.isArray(raw) && raw.length) return raw;
        } catch (e) { /* ignore */ }
        return allLabels(table).map(function (l) { return { label: l, visible: true }; });
    }

    function savePrefs(prefs) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
        } catch (e) { /* ignore */ }
    }

    // ---- sticky class for the first visible data column -----------------

    function applyStyle(el, props) {
        Object.keys(props).forEach(function (k) { el.style[k] = props[k]; });
    }

    function clearStickyStyle(el) {
        ["position", "top", "left", "zIndex", "background", "boxShadow"].forEach(function (k) {
            el.style[k] = "";
        });
        el.classList.remove("tnmt-sticky-col");
    }

    function applyStickyFirstCol(table) {
        table.style.borderCollapse = "separate";
        table.style.borderSpacing = "0";

        $$("th, td", table).forEach(function (el) {
            if (el.classList.contains("tnmt-sticky-col")) clearStickyStyle(el);
        });

        var firstTh = $$("thead th", table).find(function (th) {
            return !th.classList.contains("tnmt-col-hidden");
        });
        if (!firstTh) return;
        firstTh.classList.add("tnmt-sticky-col");
        applyStyle(firstTh, {
            position: "sticky",
            top: "0",
            left: "0",
            zIndex: "4",
            background: "#f7f7f7",
            boxShadow: "3px 0 4px -2px rgba(0,0,0,.15)",
        });

        var idx = Array.prototype.indexOf.call(firstTh.parentNode.children, firstTh);
        $$("tbody tr", table).forEach(function (tr) {
            var td = tr.children[idx];
            if (td) {
                td.classList.add("tnmt-sticky-col");
                applyStyle(td, {
                    position: "sticky",
                    left: "0",
                    zIndex: "1",
                    background: "#fff",
                    boxShadow: "3px 0 4px -2px rgba(0,0,0,.15)",
                });
            }
        });

        $$("thead th", table).forEach(function (th) {
            if (th.classList.contains("tnmt-sticky-col")) return;
            th.style.position = "sticky";
            th.style.top = "0";
            if (!th.style.zIndex) th.style.zIndex = "3";
            if (!th.style.background) th.style.background = "#f7f7f7";
        });
    }

    // ---- apply prefs to the result table --------------------------------

    function applyPrefs(table, prefs) {
        var labelSet = allLabels(table);
        var ordered = prefs.filter(function (p) { return labelSet.indexOf(p.label) !== -1; });
        var covered = ordered.map(function (p) { return p.label; });
        labelSet.forEach(function (l) {
            if (covered.indexOf(l) === -1) ordered.push({ label: l, visible: true });
        });

        if (pinnedLabel) {
            ordered = ordered.filter(function (p) { return p.label !== pinnedLabel; });
            ordered.unshift({ label: pinnedLabel, visible: true });
        }

        var ths = headerCells(table);
        var indexByLabel = {};
        ths.forEach(function (th, i) { indexByLabel[columnLabel(th)] = i; });

        var theadRow = $("thead tr", table);
        ths.forEach(function (th) { theadRow.removeChild(th); });
        ordered.forEach(function (p) {
            var th = ths.find(function (t) { return columnLabel(t) === p.label; });
            if (th) {
                th.classList.toggle("tnmt-col-hidden", !p.visible);
                theadRow.appendChild(th);
            }
        });

        $$("tbody tr", table).forEach(function (tr) {
            var allTds = Array.from(tr.children);
            allTds.forEach(function (td) { tr.removeChild(td); });
            ordered.forEach(function (p) {
                var origIdx = indexByLabel[p.label];
                if (origIdx === undefined) return;
                var td = allTds[origIdx];
                if (td) {
                    td.classList.toggle("tnmt-col-hidden", !p.visible);
                    tr.appendChild(td);
                }
            });
        });

        applyStickyFirstCol(table);
    }

    function handleSvg() {
        return '<svg class="tnmt-drag-handle" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="5" r="1.5"/><circle cx="15" cy="5" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="19" r="1.5"/><circle cx="15" cy="19" r="1.5"/></svg>';
    }

    // ---- drag-and-drop reorder -----------------------------------------

    function initDnd(list) {
        var dragging = null;

        list.addEventListener("dragstart", function (e) {
            dragging = e.target.closest(".tnmt-col-row");
            if (!dragging) return;
            dragging.classList.add("tnmt-dragging");
            e.dataTransfer.effectAllowed = "move";
        });

        list.addEventListener("dragend", function () {
            if (dragging) dragging.classList.remove("tnmt-dragging");
            $$(".tnmt-drop-target-top, .tnmt-drop-target-bottom", list).forEach(function (el) {
                el.classList.remove("tnmt-drop-target-top");
                el.classList.remove("tnmt-drop-target-bottom");
            });
            dragging = null;
        });

        list.addEventListener("dragover", function (e) {
            e.preventDefault();
            var over = e.target.closest(".tnmt-col-row");
            if (!over || over === dragging || over.classList.contains("tnmt-col-pinned")) return;
            $$(".tnmt-drop-target-top, .tnmt-drop-target-bottom", list).forEach(function (el) {
                el.classList.remove("tnmt-drop-target-top");
                el.classList.remove("tnmt-drop-target-bottom");
            });
            var rect = over.getBoundingClientRect();
            if (e.clientY < rect.top + rect.height / 2) {
                over.classList.add("tnmt-drop-target-top");
            } else {
                over.classList.add("tnmt-drop-target-bottom");
            }
        });

        list.addEventListener("dragleave", function (e) {
            var over = e.target.closest(".tnmt-col-row");
            if (over) {
                over.classList.remove("tnmt-drop-target-top");
                over.classList.remove("tnmt-drop-target-bottom");
            }
        });

        list.addEventListener("drop", function (e) {
            e.preventDefault();
            if (!dragging) return;
            var over = e.target.closest(".tnmt-col-row");
            if (!over || over === dragging || over.classList.contains("tnmt-col-pinned")) return;
            var rect = over.getBoundingClientRect();
            var insertBefore = e.clientY < rect.top + rect.height / 2;
            list.removeChild(dragging);
            if (insertBefore) {
                list.insertBefore(dragging, over);
            } else {
                over.after(dragging);
            }
            over.classList.remove("tnmt-drop-target-top");
            over.classList.remove("tnmt-drop-target-bottom");
        });
    }

    // ---- modal ----------------------------------------------------------

    function buildModal(table) {
        var prefs = loadPrefs(table);
        var labelSet = allLabels(table);

        var ordered = prefs.filter(function (p) { return labelSet.indexOf(p.label) !== -1; });
        var covered = ordered.map(function (p) { return p.label; });
        labelSet.forEach(function (l) {
            if (covered.indexOf(l) === -1) ordered.push({ label: l, visible: true });
        });

        if (pinnedLabel) {
            ordered = ordered.filter(function (p) { return p.label !== pinnedLabel; });
            ordered.unshift({ label: pinnedLabel, visible: true });
        }

        var backdrop = document.createElement("div");
        backdrop.className = "tnmt-cols-backdrop";
        var modal = document.createElement("div");
        modal.className = "tnmt-cols-modal";

        var header = document.createElement("header");
        header.textContent = "Columns";
        modal.appendChild(header);

        var list = document.createElement("div");
        list.className = "tnmt-cols-list";

        ordered.forEach(function (p) {
            var isPinned = pinnedLabel && p.label === pinnedLabel;
            var row = document.createElement("div");
            row.className = "tnmt-col-row" + (isPinned ? " tnmt-col-pinned" : "");

            var handle = document.createElement("span");
            handle.innerHTML = handleSvg();

            var cb = document.createElement("input");
            cb.type = "checkbox";
            cb.checked = true;

            if (isPinned) {
                cb.disabled = true;
            } else {
                row.draggable = true;
                row.dataset.colLabel = p.label;
                cb.dataset.colLabel = p.label;
                cb.checked = p.visible;
            }

            row.appendChild(handle);
            row.appendChild(cb);
            row.appendChild(document.createTextNode(p.label));
            list.appendChild(row);
        });

        initDnd(list);
        modal.appendChild(list);

        var footer = document.createElement("footer");
        var resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.textContent = "Reset";
        var cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.textContent = "Cancel";
        var applyBtn = document.createElement("button");
        applyBtn.type = "button";
        applyBtn.className = "tnmt-cols-apply";
        applyBtn.textContent = "Apply";
        footer.appendChild(resetBtn);
        footer.appendChild(cancelBtn);
        footer.appendChild(applyBtn);
        modal.appendChild(footer);

        function close() { backdrop.remove(); }

        resetBtn.addEventListener("click", function () {
            $$(".tnmt-col-row:not(.tnmt-col-pinned)", list).forEach(function (row) {
                row.querySelector("input[type='checkbox']").checked = true;
            });
        });
        cancelBtn.addEventListener("click", close);
        backdrop.addEventListener("click", function (e) {
            if (e.target === backdrop) close();
        });
        document.addEventListener("keydown", function onKey(e) {
            if (e.key === "Escape") {
                close();
                document.removeEventListener("keydown", onKey);
            }
        });

        applyBtn.addEventListener("click", function () {
            var newPrefs = $$(".tnmt-col-row", list).map(function (row) {
                var cb = row.querySelector("input[type='checkbox']");
                var label = row.dataset.colLabel || (pinnedLabel || "");
                return { label: label, visible: cb.checked };
            }).filter(function (p) { return p.label; });
            savePrefs(newPrefs);
            location.reload();
        });

        backdrop.appendChild(modal);
        document.body.appendChild(backdrop);
    }

    // ---- init -----------------------------------------------------------

    function bindTrigger(table) {
        var trigger = document.querySelector("[data-public-columns-trigger]");
        if (!trigger) return;
        trigger.addEventListener("click", function (e) {
            e.preventDefault();
            buildModal(table);
        });
    }

    function init() {
        var table = getTable();
        if (!table) return;
        pinnedLabel = allLabels(table)[0] || null;
        bindTrigger(table);
        applyPrefs(table, loadPrefs(table));

        // After HTMX swaps the table partial, re-apply prefs.
        document.body.addEventListener("htmx:afterSwap", function (e) {
            if (e.target && e.target.id === "tournament-table") {
                var t = getTable();
                if (t) applyPrefs(t, loadPrefs(t));
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

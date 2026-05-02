/* Tournament changelist — per-user column visibility and order.
 *
 * Gear button → modal with drag-and-drop column list + checkboxes.
 * Prefs (order + visibility) are stored in localStorage.
 */
(function () {
    "use strict";

    var STORAGE_KEY = "tnmt-changelist-cols:tournament";

    // Label of the column that is always first, non-movable, non-hideable.
    // Set in init() from the DOM before any reordering.
    var pinnedLabel = null;

    function isChangelist() {
        return /\/admin\/tournaments\/tournament\/?($|\?)/.test(location.pathname);
    }

    function $(sel, root) { return (root || document).querySelector(sel); }
    function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

    function getResultTable() {
        return document.getElementById("result_list");
    }

    // ---- column header reading ------------------------------------------

    function headerCells(table) {
        return $$("thead th", table).filter(function (th) {
            return !th.classList.contains("action-checkbox-column");
        });
    }

    function columnLabel(th) {
        return (th.textContent || "").replace(/\s+/g, " ").trim();
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
        // Default: current order, all visible.
        return allLabels(table).map(function (l) { return { label: l, visible: true }; });
    }

    function savePrefs(prefs) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
        } catch (e) { /* ignore */ }
    }

    // ---- size the results container to fill remaining viewport ----------
    // This makes BOTH scrollbars always reachable without first scrolling
    // the page, and is a prerequisite for sticky thead/td to work.

    function sizeResultsContainer() {
        // No fixed height — the page scrolls vertically; the container
        // only constrains horizontal overflow.
        var container = document.querySelector("#changelist-form .results");
        if (container) container.style.height = "";
    }

    // ---- sticky class for the first visible data column -----------------

    // Returns the px offset from the viewport left where the sticky column should pin.
    // Only counts sidebar / toggle width when they are themselves position:sticky
    // (i.e. they stay put during horizontal scroll). If our CSS makes them static,
    // they scroll with the table and the pin point is just 0.
    function getStickyLeft() {
        var toggleBtn = document.getElementById("toggle-nav-sidebar");
        var sidebar = document.getElementById("nav-sidebar");
        var toggleSticky = toggleBtn
            && getComputedStyle(toggleBtn).position === "sticky";
        var sidebarSticky = sidebar
            && getComputedStyle(sidebar).position === "sticky"
            && sidebar.getAttribute("aria-expanded") === "true";
        var left = toggleSticky ? toggleBtn.offsetWidth : 0;
        if (sidebarSticky) left += sidebar.offsetWidth;
        return left;
    }

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
        // Force border-collapse via inline style — highest priority, beats any CSS.
        table.style.borderCollapse = "separate";
        table.style.borderSpacing = "0";

        // Clear previous sticky from all cells.
        $$("th, td", table).forEach(function (el) {
            if (el.classList.contains("tnmt-sticky-col")) clearStickyStyle(el);
        });

        // --- First visible data column (corner cell: sticky at top AND left) ---
        var firstTh = $$("thead th", table).find(function (th) {
            return !th.classList.contains("action-checkbox-column")
                && !th.classList.contains("tnmt-col-hidden");
        });
        if (!firstTh) return;
        firstTh.classList.add("tnmt-sticky-col");
        var stickyLeft = getStickyLeft() + "px";
        // Corner cell needs both top and left in one assignment so the browser
        // treats it as a sticky corner rather than just horizontal sticky.
        applyStyle(firstTh, {
            position: "sticky",
            top: "0",
            left: stickyLeft,
            zIndex: "4",
            background: "var(--darkened-bg,#f8f8f8)",
            boxShadow: "3px 0 4px -2px rgba(0,0,0,.15)",
        });

        var idx = Array.prototype.indexOf.call(firstTh.parentNode.children, firstTh);
        $$("tbody tr", table).forEach(function (tr) {
            var td = tr.children[idx];
            if (td) {
                td.classList.add("tnmt-sticky-col");
                applyStyle(td, {
                    position: "sticky",
                    left: stickyLeft,
                    zIndex: "1",
                    background: "var(--body-bg,#fff)",
                    boxShadow: "3px 0 4px -2px rgba(0,0,0,.15)",
                });
            }
        });

        // --- Sticky header: all remaining ths get top:0 only ---
        $$("thead th", table).forEach(function (th) {
            if (th.classList.contains("tnmt-sticky-col")) return; // corner cell already done
            th.style.position = "sticky";
            th.style.top = "0";
            if (!th.style.zIndex) th.style.zIndex = "3";
            if (!th.style.background) th.style.background = "var(--darkened-bg,#f8f8f8)";
        });
    }

    // ---- apply prefs to the result table --------------------------------

    function applyPrefs(table, prefs) {
        var labelSet = allLabels(table);
        // Merge: keep prefs order, append any new columns from model.
        var ordered = prefs.filter(function (p) { return labelSet.indexOf(p.label) !== -1; });
        var covered = ordered.map(function (p) { return p.label; });
        labelSet.forEach(function (l) {
            if (covered.indexOf(l) === -1) ordered.push({ label: l, visible: true });
        });

        // Pinned column is always first and always visible.
        if (pinnedLabel) {
            ordered = ordered.filter(function (p) { return p.label !== pinnedLabel; });
            ordered.unshift({ label: pinnedLabel, visible: true });
        }

        // Build a map: label → original column index (in DOM order).
        var ths = headerCells(table);
        var indexByLabel = {};
        ths.forEach(function (th, i) { indexByLabel[columnLabel(th)] = i; });

        // Reorder <th> nodes inside thead > tr.
        var theadRow = $("thead tr", table);
        // Detach non-action ths.
        ths.forEach(function (th) { theadRow.removeChild(th); });
        // Re-append in preferred order.
        ordered.forEach(function (p) {
            var th = ths.find(function (t) { return columnLabel(t) === p.label; });
            if (th) {
                th.classList.toggle("tnmt-col-hidden", !p.visible);
                theadRow.appendChild(th);
            }
        });

        // Reorder <td> cells in every body row.
        $$("tbody tr", table).forEach(function (tr) {
            var allTds = Array.from(tr.children);
            // Detach.
            allTds.forEach(function (td) { tr.removeChild(td); });
            // Re-append in preferred order.
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
            $$(".tnmt-drop-target", list).forEach(function (el) {
                el.classList.remove("tnmt-drop-target");
            });
            dragging = null;
        });

        list.addEventListener("dragover", function (e) {
            e.preventDefault();
            var over = e.target.closest(".tnmt-col-row");
            if (!over || over === dragging || over.classList.contains("tnmt-col-pinned")) return;
            $$(".tnmt-drop-target", list).forEach(function (el) {
                el.classList.remove("tnmt-drop-target");
            });
            // Drop above or below based on mouse position.
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

        // Merge prefs with current columns.
        var ordered = prefs.filter(function (p) { return labelSet.indexOf(p.label) !== -1; });
        var covered = ordered.map(function (p) { return p.label; });
        labelSet.forEach(function (l) {
            if (covered.indexOf(l) === -1) ordered.push({ label: l, visible: true });
        });

        // Pinned column is always first and always visible.
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
        resetBtn.textContent = "Сбросить";
        var cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.textContent = "Отмена";
        var applyBtn = document.createElement("button");
        applyBtn.type = "button";
        applyBtn.className = "tnmt-cols-apply";
        applyBtn.textContent = "Применить";
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
            var newPrefs = $$(".tnmt-col-row:not(.tnmt-col-pinned)", list).map(function (row) {
                var cb = row.querySelector("input[type='checkbox']");
                return { label: row.dataset.colLabel, visible: cb.checked };
            });
            savePrefs(newPrefs);
            location.reload();
        });

        backdrop.appendChild(modal);
        document.body.appendChild(backdrop);
    }

    // ---- link injection into search row ------------------------------------------

    function injectGear(table) {
        if (document.querySelector(".tnmt-cols-link")) return;
        var link = document.createElement("a");
        link.href = "#";
        link.className = "tnmt-cols-link";
        link.textContent = "Настроить колонки";
        link.addEventListener("click", function (e) {
            e.preventDefault();
            buildModal(table);
        });
        var searchRow = document.getElementById("changelist-search");
        if (searchRow) {
            searchRow.appendChild(link);
        } else {
            table.parentNode.insertBefore(link, table);
        }
    }

    // ---- init -----------------------------------------------------------

    function bindTopScrollbar() {
        // Top scrollbar removed — bottom scrollbar is sufficient.
    }

    function init() {
        if (!isChangelist()) return;
        var table = getResultTable();
        if (!table) return;
        // Capture pinned label from raw DOM before any reordering.
        pinnedLabel = allLabels(table)[0] || null;
        injectGear(table);
        applyPrefs(table, loadPrefs(table));
        sizeResultsContainer();
        bindTopScrollbar();

        // Re-apply sticky left offset when the nav sidebar is toggled,
        // since the sidebar takes up space between the viewport edge and the table.
        var sidebarToggle = document.getElementById("toggle-nav-sidebar");
        if (sidebarToggle) {
            sidebarToggle.addEventListener("click", function () {
                // Django's handler fires synchronously before this one, so
                // aria-expanded is already updated; defer one frame so the
                // browser has recalculated offsetWidth before we read it.
                setTimeout(function () { applyStickyFirstCol(table); }, 0);
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

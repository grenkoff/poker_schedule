/* Unified tournament table preferences — column visibility, order, sort and filter state.
 *
 * Works on both the public list (table[data-public-columns]) and the admin
 * changelist (#result_list).  Preferences are stored server-side for
 * authenticated users (POST to __TABLE_PREFS_SAVE_URL__) and fall back to
 * localStorage for anonymous visitors.
 *
 * Column identity uses the stable `key` field from columns.py:
 *   - Public table:  th.dataset.colKey
 *   - Admin table:   extracted from th.className  "column-col_KEY"
 */
(function () {
    "use strict";

    var LS_KEY = "tnmt-changelist-cols:v2";

    // Read window globals lazily — the inline script that sets them may run
    // AFTER this module (e.g. Django admin places {{ media }} before {% block extrahead %}).
    function getServerPrefs() {
        return (typeof window.__TABLE_PREFS__ !== "undefined") ? window.__TABLE_PREFS__ : undefined;
    }
    function getSaveUrl() {
        return (typeof window.__TABLE_PREFS_SAVE_URL__ !== "undefined") ? window.__TABLE_PREFS_SAVE_URL__ : null;
    }
    function isAuthenticated() {
        var sp = getServerPrefs();
        return sp !== null && sp !== undefined;
    }

    // Detected in init() after DOMContentLoaded, because Media-class scripts
    // run in <head> before #result_list is rendered on admin pages.
    var CONTEXT = null;

    // Label of the pinned (always-first, non-movable, non-hideable) column.
    // Determined once at init from the raw DOM before any reordering.
    var pinnedKey = null;

    function $(sel, root) { return (root || document).querySelector(sel); }
    function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

    // ---- column key helpers -----------------------------------------------

    function colKeyFromTh(th) {
        // Public table: data-col-key attribute (added in _tournament_table.html).
        if (th.dataset && th.dataset.colKey) return th.dataset.colKey;
        // Admin table: Django renders class="column-col_KEY" on each th.
        var m = th.className.match(/\bcolumn-col_(\S+)\b/);
        return m ? m[1] : null;
    }

    function headerCells(table) {
        return $$("thead th", table).filter(function (th) {
            return !th.classList.contains("action-checkbox-column");
        });
    }

    function allKeys(table) {
        return headerCells(table).map(colKeyFromTh).filter(Boolean);
    }

    // Label text extracted from a th (for display in the modal only).
    // Treats <br> as a space; skips <select> content (TZ picker).
    function colLabelFromTh(th) {
        if (th.dataset && th.dataset.colLabel) return th.dataset.colLabel;
        var parts = [];
        function walk(node) {
            if (node.nodeType === 3) {
                parts.push(node.textContent);
            } else if (node.nodeType === 1) {
                if (node.tagName === "BR") parts.push(" ");
                else if (node.tagName === "SELECT") return;
                else node.childNodes.forEach(walk);
            }
        }
        walk(th);
        return parts.join("").replace(/\s+/g, " ").trim().replace(/\s*[▲▼]$/, "").trim();
    }

    // ---- preference storage -----------------------------------------------

    function getCsrfToken() {
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : "";
    }

    // The ordered column layout — array of {key, visible}. Source of truth is
    // the server (window.__TABLE_PREFS__.columns) for authenticated users,
    // localStorage otherwise.
    function loadColumns() {
        var sp = getServerPrefs();
        if (sp && Array.isArray(sp.columns) && sp.columns.length) return sp.columns;
        try {
            var raw = JSON.parse(localStorage.getItem(LS_KEY) || "null");
            if (raw && Array.isArray(raw.columns)) return raw.columns;
        } catch (e) { /* ignore */ }
        return [];
    }

    // Persist current column layout + this page's sort/filter URL state.
    // The server parses `params` (per `mode`) into a semantic sort/filter
    // record so it replays correctly on the other table.
    function persist(columns) {
        columns = columns || loadColumns();
        try { localStorage.setItem(LS_KEY, JSON.stringify({ columns: columns })); } catch (e) { /* ignore */ }

        var saveUrl = getSaveUrl();
        if (!isAuthenticated() || !saveUrl) return;

        fetch(saveUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrfToken(),
            },
            body: JSON.stringify({
                columns: columns,
                params: location.search,
                mode: CONTEXT ? CONTEXT.mode : "public",
            }),
            keepalive: true,
        }).catch(function () { /* best-effort */ });
    }

    // ---- sticky column helpers --------------------------------------------

    function applyStyle(el, props) {
        Object.keys(props).forEach(function (k) { el.style[k] = props[k]; });
    }

    function clearStickyStyle(el) {
        ["position", "top", "left", "zIndex", "background", "boxShadow"].forEach(function (k) {
            el.style[k] = "";
        });
        el.classList.remove("tnmt-sticky-col");
    }

    function getStickyLeft() {
        if (CONTEXT.mode !== "admin") return 0;
        var toggleBtn = document.getElementById("toggle-nav-sidebar");
        var sidebar = document.getElementById("nav-sidebar");
        var toggleSticky = toggleBtn && getComputedStyle(toggleBtn).position === "sticky";
        var sidebarSticky = sidebar
            && getComputedStyle(sidebar).position === "sticky"
            && sidebar.getAttribute("aria-expanded") === "true";
        var left = toggleSticky ? toggleBtn.offsetWidth : 0;
        if (sidebarSticky) left += sidebar.offsetWidth;
        return left;
    }

    function applyStickyFirstCol(table) {
        table.style.borderCollapse = "separate";
        table.style.borderSpacing = "0";

        $$("th, td", table).forEach(function (el) {
            if (el.classList.contains("tnmt-sticky-col")) clearStickyStyle(el);
        });

        var firstTh = headerCells(table).find(function (th) {
            return !th.classList.contains("tnmt-col-hidden");
        });
        if (!firstTh) return;
        firstTh.classList.add("tnmt-sticky-col");

        var stickyLeft = getStickyLeft() + "px";
        var headerBg = CONTEXT.mode === "admin" ? "var(--darkened-bg,#f8f8f8)" : "#f7f7f7";
        var bodyBg   = CONTEXT.mode === "admin" ? "var(--body-bg,#fff)"        : "#fff";

        applyStyle(firstTh, {
            position: "sticky",
            top: "0",
            left: stickyLeft,
            zIndex: "4",
            background: headerBg,
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
                    background: bodyBg,
                    boxShadow: "3px 0 4px -2px rgba(0,0,0,.15)",
                });
            }
        });

        headerCells(table).forEach(function (th) {
            if (th.classList.contains("tnmt-sticky-col")) return;
            th.style.position = "sticky";
            th.style.top = "0";
            if (!th.style.zIndex) th.style.zIndex = "3";
            if (!th.style.background) th.style.background = headerBg;
        });
    }

    // ---- apply prefs to the table -----------------------------------------

    function applyPrefs(table, savedCols) {
        var domKeys = allKeys(table);

        // Merge: saved order first (only keys present in DOM), append new keys.
        var ordered = savedCols.filter(function (p) { return domKeys.indexOf(p.key) !== -1; });
        var covered = ordered.map(function (p) { return p.key; });
        domKeys.forEach(function (k) {
            if (covered.indexOf(k) === -1) ordered.push({ key: k, visible: true });
        });

        // Pinned column is always first and always visible.
        if (pinnedKey) {
            ordered = ordered.filter(function (p) { return p.key !== pinnedKey; });
            ordered.unshift({ key: pinnedKey, visible: true });
        }

        var ths = headerCells(table);
        var indexByKey = {};
        ths.forEach(function (th, i) {
            var k = colKeyFromTh(th);
            if (k) indexByKey[k] = i;
        });

        var theadRow = $("thead tr", table);
        ths.forEach(function (th) { theadRow.removeChild(th); });
        ordered.forEach(function (p) {
            var th = ths.find(function (t) { return colKeyFromTh(t) === p.key; });
            if (th) {
                th.classList.toggle("tnmt-col-hidden", !p.visible);
                theadRow.appendChild(th);
            }
        });

        $$("tbody tr", table).forEach(function (tr) {
            var allTds = Array.from(tr.children);
            allTds.forEach(function (td) { tr.removeChild(td); });
            ordered.forEach(function (p) {
                var origIdx = indexByKey[p.key];
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

    // ---- drag-and-drop reorder --------------------------------------------

    function handleSvg() {
        return '<svg class="tnmt-drag-handle" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="5" r="1.5"/><circle cx="15" cy="5" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="19" r="1.5"/><circle cx="15" cy="19" r="1.5"/></svg>';
    }

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
            list.removeChild(dragging);
            if (e.clientY < rect.top + rect.height / 2) {
                list.insertBefore(dragging, over);
            } else {
                over.after(dragging);
            }
            over.classList.remove("tnmt-drop-target-top");
            over.classList.remove("tnmt-drop-target-bottom");
        });
    }

    // ---- modal ------------------------------------------------------------

    function buildModal(table) {
        var savedCols = loadColumns();
        var domKeys = allKeys(table);

        var ordered = savedCols.filter(function (p) { return domKeys.indexOf(p.key) !== -1; });
        var covered = ordered.map(function (p) { return p.key; });
        domKeys.forEach(function (k) {
            if (covered.indexOf(k) === -1) ordered.push({ key: k, visible: true });
        });
        if (pinnedKey) {
            ordered = ordered.filter(function (p) { return p.key !== pinnedKey; });
            ordered.unshift({ key: pinnedKey, visible: true });
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

        // Build a key→label map from current DOM headers.
        var labelByKey = {};
        headerCells(table).forEach(function (th) {
            var k = colKeyFromTh(th);
            if (k) labelByKey[k] = colLabelFromTh(th);
        });

        ordered.forEach(function (p) {
            var isPinned = pinnedKey && p.key === pinnedKey;
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
                row.dataset.colKey = p.key;
                cb.dataset.colKey = p.key;
                cb.checked = p.visible;
            }

            row.appendChild(handle);
            row.appendChild(cb);
            row.appendChild(document.createTextNode(labelByKey[p.key] || p.key));
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
            $$(".tnmt-col-row:not(.tnmt-col-pinned) input[type='checkbox']", list).forEach(function (cb) {
                cb.checked = true;
            });
        });
        cancelBtn.addEventListener("click", close);
        backdrop.addEventListener("click", function (e) {
            if (e.target === backdrop) close();
        });
        document.addEventListener("keydown", function onKey(e) {
            if (e.key === "Escape") { close(); document.removeEventListener("keydown", onKey); }
        });

        applyBtn.addEventListener("click", function () {
            var newCols = $$(".tnmt-col-row", list).map(function (row) {
                var cb = row.querySelector("input[type='checkbox']");
                var key = row.dataset.colKey || (pinnedKey || "");
                return { key: key, visible: cb ? cb.checked : true };
            }).filter(function (p) { return p.key; });

            persist(newCols);
            location.reload();
        });

        backdrop.appendChild(modal);
        document.body.appendChild(backdrop);
    }

    // ---- trigger wiring ---------------------------------------------------

    function bindTriggerPublic(table) {
        var trigger = document.querySelector("[data-public-columns-trigger]");
        if (!trigger) return;
        trigger.addEventListener("click", function (e) {
            e.preventDefault();
            buildModal(table);
        });
    }

    function injectGearAdmin(table) {
        if (document.querySelector(".tnmt-cols-link")) return;
        var link = document.createElement("a");
        link.href = "#";
        link.className = "tnmt-cols-link";
        link.textContent = "Configure columns";
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

    // ---- sort/filter state persistence ------------------------------------
    // Send the page's current URL state to the server, which parses it into a
    // semantic sort/filter record. Skip transient/empty URLs.

    function persistParams() {
        if (!location.search) return;
        if (location.search.indexOf("_reset") !== -1) return;
        persist(loadColumns());
    }

    // ---- init -------------------------------------------------------------

    function init() {
        // Detect which page we're on — done here (not at module level) because
        // Django admin's Media-class scripts are placed in <head> before the
        // result_list table is rendered, so the element doesn't exist yet at
        // IIFE evaluation time.
        var pub = document.querySelector("table[data-public-columns]");
        var adm = document.getElementById("result_list");
        if (pub) CONTEXT = { table: pub, mode: "public" };
        else if (adm) CONTEXT = { table: adm, mode: "admin" };
        if (!CONTEXT) return;

        var table = CONTEXT.table;

        // Capture pinned key from raw DOM before any reordering.
        var firstKey = allKeys(table)[0] || null;
        pinnedKey = firstKey;

        // Load and apply saved column layout.
        applyPrefs(table, loadColumns());

        if (CONTEXT.mode === "public") {
            bindTriggerPublic(table);

            // After HTMX swaps the table partial, re-apply the column layout.
            document.body.addEventListener("htmx:afterSwap", function (e) {
                if (e.target && e.target.id === "tournament-table") {
                    var t = document.querySelector("table[data-public-columns]");
                    if (t) applyPrefs(t, loadColumns());
                }
            });

            // Save sort/filter state whenever HTMX settles (URL updated via hx-push-url).
            document.body.addEventListener("htmx:afterSettle", function () {
                persistParams();
            });

        } else {
            // Admin mode.
            injectGearAdmin(table);

            // Size the results container (no fixed height needed — page scrolls).
            var container = document.querySelector("#changelist-form .results");
            if (container) container.style.height = "";

            // Re-apply sticky offset when nav sidebar is toggled.
            var sidebarToggle = document.getElementById("toggle-nav-sidebar");
            if (sidebarToggle) {
                sidebarToggle.addEventListener("click", function () {
                    setTimeout(function () { applyStickyFirstCol(table); }, 0);
                });
            }

            // Save sort/filter state on admin page init if URL has params.
            persistParams();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());

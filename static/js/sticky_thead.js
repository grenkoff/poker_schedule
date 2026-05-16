/* Sticky-top thead "ghost": mirrors the sticky-bottom proxy pattern.
 *
 * The original <thead> lives inside an X-scroll wrapper, so its CSS
 * sticky-top pins to the wrapper (which moves with page scroll) rather
 * than the viewport. To fix this we clone the thead into a sibling
 * element OUTSIDE the wrapper, apply `position: sticky; top: 0` to that
 * sibling, and sync its horizontal scroll with the wrapper. The original
 * thead is set to `visibility: hidden` to keep its column widths in
 * layout while leaving the ghost as the only visible header.
 *
 * Behavior: CSS sticky runs on the compositor thread → no jank on Y
 * scroll. X sync is JS-driven but only fires on the wrapper's scroll
 * (much less frequent than vertical page scroll).
 */
(function () {
    "use strict";

    var SELECTORS = ".public-changelist, #changelist-form .results";

    function destroyGhost(wrapper) {
        var prev = wrapper.previousElementSibling;
        if (prev && prev.classList.contains("sticky-thead-ghost")) {
            prev.remove();
        }
        // Restore original thead visibility (in case we'll re-init).
        var thead = wrapper.querySelector("thead");
        if (thead) thead.style.visibility = "";
        delete wrapper.dataset.theadGhostSetup;
    }

    function setup(wrapper) {
        if (wrapper.dataset.theadGhostSetup) return;
        var origTable = wrapper.querySelector("table");
        if (!origTable) return;
        var origThead = origTable.querySelector("thead");
        if (!origThead) return;

        wrapper.dataset.theadGhostSetup = "1";

        // Build ghost: <div.ghost overflow-x:auto> <table> <thead clone> </table> </div>
        var ghost = document.createElement("div");
        ghost.className = "sticky-thead-ghost";

        var ghostTable = document.createElement("table");
        // Copy the original table's class names so visual styling matches.
        ghostTable.className = origTable.className;
        ghostTable.style.borderCollapse = "separate";
        ghostTable.style.borderSpacing = "0";

        var ghostThead = origThead.cloneNode(true);
        ghostTable.appendChild(ghostThead);
        ghost.appendChild(ghostTable);

        wrapper.parentNode.insertBefore(ghost, wrapper);

        // Hide the original thead — ghost is now the visible header.
        origThead.style.visibility = "hidden";

        function syncWidths() {
            var origThs = origThead.children[0]
                ? origThead.children[0].children
                : [];
            var cloneThs = ghostThead.children[0]
                ? ghostThead.children[0].children
                : [];
            for (var i = 0; i < origThs.length && i < cloneThs.length; i++) {
                var w = origThs[i].offsetWidth;
                cloneThs[i].style.width = w + "px";
                cloneThs[i].style.minWidth = w + "px";
                cloneThs[i].style.maxWidth = w + "px";
            }
            ghostTable.style.width = origTable.scrollWidth + "px";
            ghostTable.style.minWidth = origTable.scrollWidth + "px";
            // After re-measuring height of ghost, pull subsequent content up.
            ghost.style.marginBottom = "-" + ghost.offsetHeight + "px";
            // Initial scroll sync.
            ghost.scrollLeft = wrapper.scrollLeft;
        }

        // Wait for layout to settle before measuring.
        requestAnimationFrame(function () {
            syncWidths();
            // Clone <select> doesn't copy `.value` (cloneNode copies attrs,
            // not properties) — selectedIndex on the clone is 0, which
            // shows the first option (e.g. UTC-12). Re-sync via localize.
            window.dispatchEvent(new Event("sticky-thead-rebuilt"));
        });

        wrapper.addEventListener(
            "scroll",
            function () { ghost.scrollLeft = wrapper.scrollLeft; },
            { passive: true }
        );
        window.addEventListener("resize", syncWidths);
        if (window.ResizeObserver) {
            new ResizeObserver(syncWidths).observe(wrapper);
        }
    }

    function rescan() {
        document.querySelectorAll(SELECTORS).forEach(setup);
    }

    function init() {
        rescan();
        if (document.body) {
            document.body.addEventListener("htmx:afterSwap", function () {
                // The whole #tournament-table block was replaced — any old
                // ghost sibling is gone with it. Just re-scan.
                setTimeout(rescan, 0);
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    // Expose for debugging.
    window.__rebuildStickyThead = function () {
        document.querySelectorAll(SELECTORS).forEach(destroyGhost);
        rescan();
    };
})();

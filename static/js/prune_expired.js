/* Remove tournament rows from the public table once their late
 * registration window has closed, without waiting for a server poll
 * or page reload. Each <tr> carries `data-late-reg-at="<iso>"`; we
 * compare to wall-clock now and drop expired rows on a 30 s tick.
 *
 * Pairs with the HTMX `hx-trigger="every 300s"` on #tournament-table
 * that catches longer-horizon server changes (new tournaments,
 * edits) every 5 minutes.
 */
(function () {
    "use strict";

    var TICK_MS = 30 * 1000;
    var _timer = null;

    function prune() {
        var now = Date.now();
        var rows = document.querySelectorAll("tr[data-late-reg-at]");
        for (var i = 0; i < rows.length; i++) {
            var iso = rows[i].getAttribute("data-late-reg-at");
            if (!iso) continue;
            var t = Date.parse(iso);
            if (isNaN(t)) continue;
            if (t < now) {
                rows[i].remove();
            }
        }
    }

    function restart() {
        if (_timer !== null) {
            clearInterval(_timer);
        }
        // Prune once right away so already-stale rows (e.g. server
        // rendered the page seconds ago) disappear without a tick wait.
        prune();
        _timer = setInterval(prune, TICK_MS);
    }

    function init() {
        restart();
        // HTMX swaps replace the table contents but keep the outer
        // #tournament-table div; rebind so the next tick sees the new
        // rows and old timers don't pile up.
        if (document.body) {
            document.body.addEventListener("htmx:afterSwap", restart);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

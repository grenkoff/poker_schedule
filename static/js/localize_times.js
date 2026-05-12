/* Convert <time data-local-dt datetime="ISO-UTC"> to the browser's local
 * timezone after page load (and after HTMX swaps). The ISO datetime is the
 * source of truth; the server-rendered text is just a no-JS fallback.
 */
(function () {
    "use strict";

    function pad(n) { return n < 10 ? "0" + n : "" + n; }

    function format(date) {
        var dd = pad(date.getDate());
        var mm = pad(date.getMonth() + 1);
        var yyyy = date.getFullYear();
        var hh = pad(date.getHours());
        var mi = pad(date.getMinutes());
        var tz = "";
        try {
            var parts = new Intl.DateTimeFormat(undefined, {
                timeZoneName: "short",
            }).formatToParts(date);
            var tzPart = parts.find(function (p) { return p.type === "timeZoneName"; });
            if (tzPart) tz = " " + tzPart.value;
        } catch (e) { /* ignore */ }
        return dd + "." + mm + "." + yyyy + " " + hh + ":" + mi + tz;
    }

    function localize(root) {
        var nodes = (root || document).querySelectorAll("time[data-local-dt]");
        nodes.forEach(function (el) {
            if (el.dataset.localized) return;
            var iso = el.getAttribute("datetime");
            if (!iso) return;
            var d = new Date(iso);
            if (isNaN(d.getTime())) return;
            el.textContent = format(d);
            el.dataset.localized = "1";
        });
    }

    function init() {
        localize();
        if (document.body) {
            document.body.addEventListener("htmx:afterSwap", function (e) {
                localize(e.target);
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

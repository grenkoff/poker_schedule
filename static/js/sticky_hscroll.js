/* For each wide table wrapper, inject a thin sticky horizontal scrollbar
 * sibling that stays pinned to the viewport bottom while the table is in
 * view. The wrapper's own scrollbar is hidden via CSS; this proxy is the
 * only visible scrollbar. Proxy and wrapper share the same scrollLeft.
 *
 * Behavior: `position: sticky; bottom: 0` on the proxy keeps it at
 * viewport bottom while its natural position is below the fold; once the
 * page is scrolled to the end of the table, the proxy releases and sits
 * between the table and the pagination — its natural position.
 */
(function () {
    "use strict";

    var SELECTORS = ".public-changelist, #changelist-form .results";

    function setup(host) {
        if (host.dataset.hscrollSetup) return;
        host.dataset.hscrollSetup = "1";

        var proxy = document.createElement("div");
        proxy.className = "hscroll-proxy";
        var inner = document.createElement("div");
        inner.className = "hscroll-proxy-inner";
        proxy.appendChild(inner);

        host.parentNode.insertBefore(proxy, host.nextSibling);

        var syncing = false;
        function fromHost() {
            if (syncing) return;
            syncing = true;
            proxy.scrollLeft = host.scrollLeft;
            syncing = false;
        }
        function fromProxy() {
            if (syncing) return;
            syncing = true;
            host.scrollLeft = proxy.scrollLeft;
            syncing = false;
        }
        function update() {
            inner.style.width = host.scrollWidth + "px";
            proxy.style.display =
                host.scrollWidth > host.clientWidth + 1 ? "" : "none";
        }

        host.addEventListener("scroll", fromHost, { passive: true });
        proxy.addEventListener("scroll", fromProxy, { passive: true });
        window.addEventListener("resize", update);
        if (window.ResizeObserver) {
            new ResizeObserver(update).observe(host);
        }
        update();
    }

    function rescan() {
        document.querySelectorAll(SELECTORS).forEach(setup);
        document.querySelectorAll(".hscroll-proxy").forEach(function (p) {
            var host = p.previousElementSibling;
            if (!host) return;
            p.firstChild.style.width = host.scrollWidth + "px";
            p.style.display =
                host.scrollWidth > host.clientWidth + 1 ? "" : "none";
        });
    }

    function init() {
        rescan();
        if (document.body) {
            document.body.addEventListener("htmx:afterSwap", function () {
                setTimeout(rescan, 0);
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

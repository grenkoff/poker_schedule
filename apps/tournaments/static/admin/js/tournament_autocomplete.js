/* Typeahead dropdown for the tournament changelist search box.
 *
 * As you type, fetches matching tournaments from `autocomplete-json/` and
 * shows a dropdown. Navigate with ↑/↓, open the highlighted tournament with
 * Enter, dismiss with Esc. Click a row to open it. With nothing highlighted,
 * Enter falls back to the normal admin search.
 */
(function () {
    "use strict";

    function onlyOnChangelist() {
        // Tournament changelist URL ends with /admin/tournaments/tournament/.
        return /\/admin\/tournaments\/tournament\/?$/.test(location.pathname);
    }

    function debounce(fn, ms) {
        var t = null;
        return function () {
            var args = arguments, self = this;
            clearTimeout(t);
            t = setTimeout(function () { fn.apply(self, args); }, ms);
        };
    }

    function init() {
        if (!onlyOnChangelist()) return;
        var input = document.getElementById("searchbar");
        if (!input) return;

        var endpoint = location.pathname.replace(/\/?$/, "/") + "autocomplete-json/";

        // Wrap the input so the absolutely-positioned dropdown aligns to it.
        var wrap = document.createElement("span");
        wrap.className = "tnmt-ac-wrap";
        input.parentNode.insertBefore(wrap, input);
        wrap.appendChild(input);

        var list = document.createElement("ul");
        list.className = "tnmt-ac-list";
        list.setAttribute("role", "listbox");
        list.hidden = true;
        wrap.appendChild(list);

        // Clear (×) button inside the input, shown only when there's text.
        var clearBtn = document.createElement("button");
        clearBtn.type = "button";
        clearBtn.className = "tnmt-ac-clear";
        clearBtn.setAttribute("aria-label", "Clear search");
        clearBtn.innerHTML = "&times;";
        wrap.appendChild(clearBtn);

        function toggleClear() { clearBtn.hidden = !input.value; }

        input.setAttribute("autocomplete", "off");

        var items = [];     // [{name, room, url}]
        var active = -1;    // highlighted index
        var lastQuery = null;
        var seq = 0;        // guards out-of-order responses

        function close() {
            list.hidden = true;
            list.innerHTML = "";
            items = [];
            active = -1;
        }

        function setActive(i) {
            var rows = list.children;
            if (active >= 0 && rows[active]) rows[active].classList.remove("tnmt-ac-active");
            active = i;
            if (active >= 0 && rows[active]) {
                rows[active].classList.add("tnmt-ac-active");
                rows[active].scrollIntoView({ block: "nearest" });
            }
        }

        function render() {
            list.innerHTML = "";
            if (!items.length) { list.hidden = true; return; }
            items.forEach(function (it, idx) {
                var li = document.createElement("li");
                li.className = "tnmt-ac-item";
                li.setAttribute("role", "option");
                var name = document.createElement("span");
                name.className = "tnmt-ac-name";
                name.textContent = it.name;
                var room = document.createElement("span");
                room.className = "tnmt-ac-room";
                room.textContent = it.room || "";
                li.appendChild(name);
                li.appendChild(room);
                li.addEventListener("mouseenter", function () { setActive(idx); });
                li.addEventListener("mousedown", function (e) {
                    // mousedown (not click) so it fires before input blur.
                    e.preventDefault();
                    window.location.href = it.url;
                });
                list.appendChild(li);
            });
            active = -1;
            list.hidden = false;
        }

        var fetchSuggestions = debounce(function () {
            var q = input.value.trim();
            if (q === lastQuery) return;
            lastQuery = q;
            if (!q) { close(); return; }
            var mySeq = ++seq;
            fetch(endpoint + "?q=" + encodeURIComponent(q), {
                credentials: "same-origin",
                headers: { "Accept": "application/json" },
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (mySeq !== seq) return;  // a newer request superseded this
                    items = (data && data.results) || [];
                    render();
                })
                .catch(function () { /* ignore */ });
        }, 180);

        input.addEventListener("input", fetchSuggestions);
        input.addEventListener("input", toggleClear);

        clearBtn.addEventListener("click", function () {
            input.value = "";
            lastQuery = null;
            close();
            toggleClear();
            input.focus();
        });

        input.addEventListener("keydown", function (e) {
            if (list.hidden || !items.length) return;
            if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((active + 1) % items.length);
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((active - 1 + items.length) % items.length);
            } else if (e.key === "Enter") {
                if (active >= 0 && items[active]) {
                    e.preventDefault();  // open the highlighted tournament
                    window.location.href = items[active].url;
                }
                // else: let the form submit the normal search
            } else if (e.key === "Escape") {
                close();
            }
        });

        input.addEventListener("focus", function () {
            if (items.length) list.hidden = false;
        });

        document.addEventListener("click", function (e) {
            if (!wrap.contains(e.target)) close();
        });

        toggleClear();  // input may arrive pre-filled (e.g. ?q= in the URL)
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());

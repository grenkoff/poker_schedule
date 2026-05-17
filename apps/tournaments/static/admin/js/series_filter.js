/* On the Tournament admin form, the "Tournament series" select is
 * server-rendered with every series across every room (each <option>
 * carries data-room-id). This script:
 *   - disables the series select whenever Room is unset
 *   - hides options whose data-room-id doesn't match the selected Room
 *   - clears the series selection if the user changes rooms and the
 *     previously-picked series isn't valid for the new room.
 *
 * The Room field is `autocomplete_fields = ("room",)` in the admin →
 * select2-driven; select2 fires the standard `change` event on the
 * underlying <select>, so we can just listen for it.
 */
(function () {
    "use strict";

    function init() {
        var seriesSelect = document.querySelector('select[data-tnmt-series="1"]');
        if (!seriesSelect) return;
        // Admin uses id_room for the Room FK; raw_id/autocomplete still
        // exposes the underlying <select> at that id.
        var roomSelect = document.getElementById("id_room");
        if (!roomSelect) return;

        var placeholder = ensurePlaceholder(seriesSelect);

        function selectedRoomId() {
            var v = roomSelect.value;
            return v ? String(v) : "";
        }

        function filterOptions() {
            var room = selectedRoomId();
            var current = seriesSelect.value;
            var stillValid = false;

            Array.prototype.forEach.call(seriesSelect.options, function (opt) {
                if (opt === placeholder) return;
                var rid = opt.getAttribute("data-room-id") || "";
                if (room && rid === room) {
                    opt.hidden = false;
                    opt.disabled = false;
                    if (opt.value === current) stillValid = true;
                } else {
                    opt.hidden = true;
                    opt.disabled = true;
                }
            });

            if (!room) {
                seriesSelect.disabled = true;
                seriesSelect.value = "";
            } else {
                seriesSelect.disabled = false;
                if (!stillValid) seriesSelect.value = "";
            }
        }

        roomSelect.addEventListener("change", filterOptions);
        // select2 sometimes triggers via jQuery — also wire a jQuery
        // listener if jQuery is on the page (admin always loads it).
        if (window.django && window.django.jQuery) {
            window.django.jQuery(roomSelect).on("change", filterOptions);
        }
        filterOptions();
    }

    /* If there's no blank option, the select can't represent the
     * "unselected" state. Admin's ModelChoiceField already injects one
     * (empty_label) for nullable FKs; for required FKs it doesn't.
     * Insert a blank "---------" if missing so users can clear. */
    function ensurePlaceholder(sel) {
        var first = sel.options[0];
        if (first && first.value === "") return first;
        var ph = document.createElement("option");
        ph.value = "";
        ph.textContent = "---------";
        sel.insertBefore(ph, sel.firstChild);
        return ph;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

// After a failed submit, Django admin renders "This field is required"
// (or its translation) as an `.errorlist` inside `.form-row`. We strip
// that inline message on load — keeping the red border so the editor
// still sees which fields need attention — and rewrite the top banner
// to a plainer "fill the required fields" wording.
//
// Real validation errors (where the field has a value but it's invalid)
// stay visible: we only drop the inline list when the field is empty,
// which is exactly the "required" case.
//
// As the editor fills any erroring row, the red border also goes away.
(function () {
    "use strict";

    var TOP_BANNER_TEXT = "Заполните обязательные поля.";

    var REQUIRED_MESSAGES = [
        "Обязательное поле.",
        "This field is required.",
    ];

    function dropInlineRequiredMessages() {
        // Strip the literal "required" line from every errorlist on the
        // page (main form rows AND tabular inline cells) — leaving any
        // real validation errors visible. The red border on the row stays
        // because it comes from the `.errors` class we don't touch.
        document.querySelectorAll(".errorlist").forEach(function (errorlist) {
            errorlist.querySelectorAll("li").forEach(function (li) {
                if (REQUIRED_MESSAGES.indexOf((li.textContent || "").trim()) !== -1) {
                    li.remove();
                }
            });
            if (!errorlist.querySelector("li")) {
                errorlist.remove();
            }
        });
    }

    function rewriteTopBanner() {
        document.querySelectorAll(".errornote").forEach(function (note) {
            note.textContent = TOP_BANNER_TEXT;
        });
    }

    function clearRowOnInput(row, field) {
        if ((field.value || "").trim() === "") {
            return;
        }
        var errorlist = row.querySelector(".errorlist");
        if (errorlist) {
            errorlist.remove();
        }
        row.classList.remove("errors");
    }

    function attachListeners() {
        var $ = window.django && window.django.jQuery;
        document.querySelectorAll(".form-row.errors").forEach(function (row) {
            var fields = row.querySelectorAll("input, select, textarea");
            fields.forEach(function (field) {
                if (field.type === "hidden") {
                    return;
                }
                ["input", "change"].forEach(function (event) {
                    field.addEventListener(event, function () {
                        clearRowOnInput(row, field);
                    });
                });
                if ($ && field.tagName === "SELECT") {
                    $(field).on("change select2:select select2:unselect", function () {
                        clearRowOnInput(row, field);
                    });
                }
            });
        });
    }

    function init() {
        rewriteTopBanner();
        dropInlineRequiredMessages();
        attachListeners();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

/* Tournament admin — Time fieldset behaviour.
 *
 * Owns four interlocked changes on top of Django's AdminSplitDateTime widget:
 *  - Strip the redundant "Now | clock-icon" / standalone-calendar-icon
 *    shortcuts that Django injects beside each input.
 *  - Make the date input itself the trigger for the calendar popup.
 *  - On a fresh add form: prefill today's date and the user's local TZ.
 *  - Compute "late_registration_duration" from the two times and gate the
 *    late-reg time input until the starting time is set.
 *
 * Django's DateTimeShortcuts.init runs on `window.load` and only then
 * inserts the `<span class="datetimeshortcuts">` siblings with the
 * calendar/clock links. We MUST run after that — DOMContentLoaded is
 * too early. The shortcuts object is also wrapped in a block scope and
 * not exposed globally, so we trigger the picker by dispatching a click
 * on the existing (hidden) `<a id="calendarlink<num>">` link.
 */
(function () {
    "use strict";

    function $(sel, root) { return (root || document).querySelector(sel); }
    function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

    function pad(n) { return n < 10 ? "0" + n : "" + n; }

    function todayDdmmyyyy() {
        const d = new Date();
        return pad(d.getDate()) + "." + pad(d.getMonth() + 1) + "." + d.getFullYear();
    }

    function nowHhmm() {
        const d = new Date();
        return pad(d.getHours()) + ":" + pad(d.getMinutes());
    }

    function parseDdmmyyyyHhmm(dateStr, timeStr) {
        const dm = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec((dateStr || "").trim());
        const tm = /^(\d{1,2}):(\d{2})$/.exec((timeStr || "").trim());
        if (!dm || !tm) return null;
        const d = new Date(
            parseInt(dm[3], 10), parseInt(dm[2], 10) - 1, parseInt(dm[1], 10),
            parseInt(tm[1], 10), parseInt(tm[2], 10), 0, 0
        );
        return isNaN(d.getTime()) ? null : d;
    }

    function parseDdmmyyyy(s) {
        const m = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec((s || "").trim());
        if (!m) return null;
        const d = new Date(parseInt(m[3], 10), parseInt(m[2], 10) - 1, parseInt(m[1], 10), 0, 0, 0, 0);
        return isNaN(d.getTime()) ? null : d;
    }

    function sameYMD(a, b) {
        return a.getFullYear() === b.getFullYear()
            && a.getMonth() === b.getMonth()
            && a.getDate() === b.getDate();
    }

    function formatDuration(minutes) {
        const m = Math.max(0, Math.floor(minutes));
        return Math.floor(m / 60) + "h " + (m % 60) + "min";
    }

    /* --- custom time picker -------------------------------------------- */

    let _timePopup = null;
    let _activeTimeInput = null;

    function buildTimePopup() {
        const popup = document.createElement("div");
        popup.className = "tnmt-time-popup";
        popup.style.display = "none";
        const cols = document.createElement("div");
        cols.className = "tnmt-time-cols";

        function makeCol(kind, label, count) {
            const wrap = document.createElement("div");
            wrap.className = "tnmt-time-col";
            wrap.dataset.kind = kind;
            const header = document.createElement("div");
            header.className = "tnmt-time-col-header";
            header.textContent = label;
            wrap.appendChild(header);
            for (let i = 0; i < count; i++) {
                const cell = document.createElement("div");
                cell.className = "tnmt-time-cell";
                cell.dataset.value = pad(i);
                cell.textContent = pad(i);
                wrap.appendChild(cell);
            }
            return wrap;
        }
        cols.appendChild(makeCol("h", "ч", 24));
        cols.appendChild(makeCol("m", "мин", 60));
        popup.appendChild(cols);
        document.body.appendChild(popup);

        popup.addEventListener("click", function (e) {
            const cell = e.target.closest(".tnmt-time-cell");
            if (!cell || !_activeTimeInput) return;
            e.stopPropagation();
            if (cell.classList.contains("tnmt-time-cell-disabled")) return;
            const col = cell.parentNode;
            const kind = col.dataset.kind;
            const v = cell.dataset.value;
            const m = (_activeTimeInput.value || "").match(/^(\d{1,2}):(\d{2})$/);
            let hh = m ? pad(parseInt(m[1], 10)) : "00";
            let mm = m ? m[2] : "00";
            if (kind === "h") hh = v; else mm = v;
            // Picking a new hour can shift which minutes are valid; if
            // the resulting minute would now be invalid, snap to the min.
            if (kind === "h") {
                const minMin = minMinuteForHour(parseInt(hh, 10));
                if (parseInt(mm, 10) < minMin) mm = pad(minMin);
            }
            _activeTimeInput.value = hh + ":" + mm;
            _activeTimeInput.dispatchEvent(new Event("input", { bubbles: true }));
            _activeTimeInput.dispatchEvent(new Event("change", { bubbles: true }));
            markSelected(popup, hh, mm);
            refreshTimePopupDisabled();
        });

        document.addEventListener("click", function (e) {
            if (popup.style.display === "none") return;
            if (popup.contains(e.target)) return;
            if (e.target === _activeTimeInput) return;
            popup.style.display = "none";
        });

        return popup;
    }

    function markSelected(popup, hh, mm) {
        $$(".tnmt-time-cell", popup).forEach(function (c) {
            c.classList.remove("tnmt-time-cell-selected");
        });
        const hCell = popup.querySelector('[data-kind="h"] .tnmt-time-cell[data-value="' + hh + '"]');
        const mCell = popup.querySelector('[data-kind="m"] .tnmt-time-cell[data-value="' + mm + '"]');
        if (hCell) {
            hCell.classList.add("tnmt-time-cell-selected");
            hCell.scrollIntoView({ block: "nearest" });
        }
        if (mCell) {
            mCell.classList.add("tnmt-time-cell-selected");
            mCell.scrollIntoView({ block: "nearest" });
        }
    }

    function ensureTimePopup() {
        if (!_timePopup) _timePopup = buildTimePopup();
        return _timePopup;
    }

    /** Returns the minimum allowed minute when picking the late-reg time
     *  in the given hour, given the current starting time. Returns 0 when
     *  the constraint doesn't apply. */
    function minMinuteForHour(hour) {
        if (!_activeTimeInput || _activeTimeInput.name !== "late_reg_at_1") return 0;
        const f = fields();
        const start = parseDdmmyyyyHhmm(f.startDate && f.startDate.value, f.startTime && f.startTime.value);
        const lateD = parseDdmmyyyy(f.lateDate && f.lateDate.value);
        if (!start || !lateD || !sameYMD(start, lateD)) return 0;
        if (hour === start.getHours()) return start.getMinutes();
        return 0;
    }

    function refreshTimePopupDisabled() {
        const popup = _timePopup;
        if (!popup || !_activeTimeInput) return;
        $$(".tnmt-time-cell", popup).forEach(function (c) {
            c.classList.remove("tnmt-time-cell-disabled");
        });
        if (_activeTimeInput.name !== "late_reg_at_1") return;
        const f = fields();
        const start = parseDdmmyyyyHhmm(f.startDate && f.startDate.value, f.startTime && f.startTime.value);
        const lateD = parseDdmmyyyy(f.lateDate && f.lateDate.value);
        if (!start) return;
        if (!lateD || !sameYMD(start, lateD)) return; // different day → no constraint
        const startHour = start.getHours();
        const startMin = start.getMinutes();
        $$('[data-kind="h"] .tnmt-time-cell', popup).forEach(function (c) {
            if (parseInt(c.dataset.value, 10) < startHour) {
                c.classList.add("tnmt-time-cell-disabled");
            }
        });
        const m = (_activeTimeInput.value || "").match(/^(\d{1,2}):(\d{2})$/);
        const curHour = m ? parseInt(m[1], 10) : startHour;
        if (curHour <= startHour) {
            $$('[data-kind="m"] .tnmt-time-cell', popup).forEach(function (c) {
                if (parseInt(c.dataset.value, 10) < startMin) {
                    c.classList.add("tnmt-time-cell-disabled");
                }
            });
        }
    }

    function closeOtherPickers() {
        $$(".calendarbox").forEach(function (b) { b.style.display = "none"; });
    }

    function closeTimePopup() {
        if (_timePopup) _timePopup.style.display = "none";
    }

    function openTimePopup(timeInput) {
        const popup = ensureTimePopup();
        // Toggle: a second click on the active input closes the popup.
        if (popup.style.display === "block" && _activeTimeInput === timeInput) {
            popup.style.display = "none";
            return;
        }
        closeOtherPickers();
        _activeTimeInput = timeInput;
        const r = timeInput.getBoundingClientRect();
        popup.style.left = (r.left + window.scrollX) + "px";
        popup.style.top = (r.bottom + window.scrollY + 4) + "px";
        popup.style.display = "block";
        const m = (timeInput.value || "").match(/^(\d{1,2}):(\d{2})$/);
        const hh = m ? pad(parseInt(m[1], 10)) : "00";
        const mm = m ? m[2] : "00";
        markSelected(popup, hh, mm);
        refreshTimePopupDisabled();
    }

    /* ------------------------------------------------------------------- */

    /**
     * The split_datetime.html template puts both inputs in the SAME
     * `<p class="datetime">` parent, so we cannot find an input's
     * shortcuts span via `parent.querySelector(".datetimeshortcuts")` —
     * it would return the first one (the date's) for the time input too.
     * Django inserts the span as the input's next sibling.
     */
    function shortcutsAfter(input) {
        let n = input.nextSibling;
        while (n) {
            if (n.nodeType === Node.ELEMENT_NODE && n.classList.contains("datetimeshortcuts")) {
                return n;
            }
            n = n.nextSibling;
        }
        return null;
    }

    /**
     * Replace Django's calendar/clock shortcuts:
     *  - Date row: hide standalone calendar-icon link (keep it in the DOM
     *    so its position anchors the popup), strip the " | " separator,
     *    and bind the date input itself to dispatch a click on that link.
     *  - Time row: drop the shortcuts span (Now/clock) and any TZ warning.
     */
    function rewireDateTimeShortcuts() {
        $$("input.tnmt-date-trigger").forEach(function (dateInput) {
            const shortcuts = shortcutsAfter(dateInput);
            let calLink = null;
            if (shortcuts) {
                // Django's "Today" uses DateTimeShortcuts.now(), which
                // honours `body[data-admin-utc-offset]` — i.e. the SERVER
                // day, not the browser's local day. Replace the listener
                // with one that always writes the user's local today.
                const todayLink = shortcuts.querySelector("a:not([id^='calendarlink'])");
                if (todayLink) {
                    const fresh = todayLink.cloneNode(true);
                    todayLink.parentNode.replaceChild(fresh, todayLink);
                    fresh.addEventListener("click", function (e) {
                        e.preventDefault();
                        dateInput.value = todayDdmmyyyy();
                        dateInput.dispatchEvent(new Event("input", { bubbles: true }));
                        dateInput.dispatchEvent(new Event("change", { bubbles: true }));
                    });
                }
                calLink = shortcuts.querySelector('a[id^="calendarlink"]');
                if (calLink) {
                    const prev = calLink.previousSibling;
                    if (prev && prev.nodeType === Node.TEXT_NODE) prev.remove();
                    calLink.style.position = "absolute";
                    calLink.style.left = "0";
                    calLink.style.top = "0";
                    calLink.style.width = "0";
                    calLink.style.height = "0";
                    calLink.style.overflow = "hidden";
                    calLink.style.opacity = "0";
                    calLink.setAttribute("tabindex", "-1");
                    calLink.setAttribute("aria-hidden", "true");
                }
            }
            if (calLink) {
                dateInput.addEventListener("click", function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (dateInput.disabled) return;
                    const num = calLink.id.replace(/^calendarlink/, "");
                    const box = document.getElementById("calendarbox" + num);
                    // Toggle: a second click on the same date input closes
                    // its already-open calendar.
                    if (box && box.style.display === "block") {
                        box.style.display = "none";
                        return;
                    }
                    closeTimePopup();
                    closeOtherPickers();
                    calLink.click();
                    if (box) {
                        const r = dateInput.getBoundingClientRect();
                        box.style.left = (r.left + window.scrollX) + "px";
                        box.style.top = (r.bottom + window.scrollY + 4) + "px";
                    }
                });
            }
        });
        $$("input.tnmt-time-input").forEach(function (timeInput) {
            const shortcuts = shortcutsAfter(timeInput);
            if (shortcuts) shortcuts.remove();
            const warn = timeInput.parentNode.querySelector(".timezonewarning");
            if (warn) warn.remove();
            timeInput.addEventListener("click", function (e) {
                if (timeInput.disabled) return;
                e.preventDefault();
                e.stopPropagation();
                openTimePopup(timeInput);
            });
            // "Сейчас" link, mirrors Django's "Сегодня" next to date.
            const nowSpan = document.createElement("span");
            nowSpan.className = "datetimeshortcuts tnmt-now-shortcut";
            const nowLink = document.createElement("a");
            nowLink.href = "#";
            nowLink.textContent = window.gettext ? window.gettext("Now") : "Сейчас";
            nowLink.addEventListener("click", function (e) {
                e.preventDefault();
                if (timeInput.disabled) return;
                timeInput.value = nowHhmm();
                timeInput.dispatchEvent(new Event("input", { bubbles: true }));
                timeInput.dispatchEvent(new Event("change", { bubbles: true }));
            });
            nowSpan.appendChild(document.createTextNode(" "));
            nowSpan.appendChild(nowLink);
            timeInput.parentNode.insertBefore(nowSpan, timeInput.nextSibling);
        });
    }

    function isAddForm() {
        const meta = document.getElementById("tnmt-user-tz");
        return meta && meta.dataset.isAdd === "1";
    }

    function applyDefaults() {
        const tzSelect = document.getElementById("id_timezone");
        if (tzSelect && isAddForm() && (tzSelect.value === "" || tzSelect.value === "UTC")) {
            const meta = document.getElementById("tnmt-user-tz");
            const userTz = meta ? meta.dataset.userTz : null;
            let target = null;
            try {
                target = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
            } catch (_) { /* ignore */ }
            target = target || userTz;
            if (target) {
                const opt = Array.from(tzSelect.options).find(function (o) { return o.value === target; });
                if (opt) tzSelect.value = target;
            }
        }
        if (isAddForm()) {
            $$("input.tnmt-date-trigger").forEach(function (inp) {
                if (!inp.value) inp.value = todayDdmmyyyy();
            });
            $$("input.tnmt-time-input").forEach(function (inp) {
                if (!inp.value && !inp.disabled) inp.value = nowHhmm();
            });
        }
    }

    /** late_reg_at time stays disabled until starting_time time is set. */
    function gateLateRegTime() {
        const startTime = $('input.tnmt-time-input[name="starting_time_1"]');
        const lateTime = $('input.tnmt-time-input[name="late_reg_at_1"]');
        if (!startTime || !lateTime) return;
        function refresh() {
            if (!isLateAvailable()) {
                lateTime.disabled = true;
                return;
            }
            const ok = /^\d{1,2}:\d{2}$/.test((startTime.value || "").trim());
            lateTime.disabled = !ok;
            if (!ok) lateTime.value = "";
        }
        startTime.addEventListener("input", refresh);
        startTime.addEventListener("change", refresh);
        refresh();
    }

    function isLateAvailable() {
        const cb = document.getElementById("id_late_registration_available");
        return !cb || cb.checked;
    }

    /** Toggle the entire late-reg row (date + time + level + Now link)
     *  on/off in step with the "Late registration available" checkbox.
     *  When off: stash the current date/time/level values and blank +
     *  disable the inputs. When toggled back on: restore the stashed
     *  values. Server-side clean() still pins safe defaults if the form
     *  is submitted while the checkbox is off. */
    function bindLateRegAvailableToggle() {
        const cb = document.getElementById("id_late_registration_available");
        if (!cb) return;
        const lateDate = $('input.tnmt-date-trigger[name="late_reg_at_0"]');
        const lateTime = $('input.tnmt-time-input[name="late_reg_at_1"]');
        const lateLevel = document.getElementById("id_late_reg_level");
        const lateRow = lateDate ? lateDate.closest("p.datetime") : null;

        const stash = { date: null, time: null, level: null };
        let lastOff = !cb.checked;
        const labelRows = [
            document.querySelector(".form-row.field-late_reg_at"),
            document.querySelector(".form-row.field-late_reg_level"),
            document.querySelector(".form-row.field-late_registration_duration"),
        ].filter(Boolean);

        function refresh() {
            const off = !cb.checked;
            const turningOff = off && !lastOff;
            const turningOn = !off && lastOff;
            if (turningOff) {
                stash.date = lateDate ? lateDate.value : "";
                stash.time = lateTime ? lateTime.value : "";
                stash.level = lateLevel ? lateLevel.value : "";
            }
            if (lateDate) {
                lateDate.disabled = off;
                if (turningOff) {
                    lateDate.value = "";
                    lateDate.dataset.tnmtPlaceholder = lateDate.placeholder || "";
                    lateDate.placeholder = "";
                } else if (turningOn) {
                    lateDate.value = stash.date || "";
                    if (lateDate.dataset.tnmtPlaceholder !== undefined) {
                        lateDate.placeholder = lateDate.dataset.tnmtPlaceholder;
                    }
                }
            }
            if (lateTime) {
                lateTime.disabled = off;
                if (turningOff) lateTime.value = "";
                else if (turningOn) lateTime.value = stash.time || "";
            }
            if (lateLevel) {
                lateLevel.disabled = off;
                if (turningOff) lateLevel.value = "";
                else if (turningOn) lateLevel.value = stash.level || "";
            }
            if (lateRow) {
                lateRow.querySelectorAll("a").forEach(function (a) {
                    if (off) {
                        a.style.pointerEvents = "none";
                        a.style.opacity = "0.5";
                    } else {
                        a.style.pointerEvents = "";
                        a.style.opacity = "";
                    }
                });
            }
            labelRows.forEach(function (row) {
                row.classList.toggle("tnmt-optional", off);
            });
            if (off) {
                closeTimePopup();
                closeOtherPickers();
                const f = fields();
                if (f.duration) f.duration.value = "";
            } else {
                const startTime = $('input.tnmt-time-input[name="starting_time_1"]');
                if (lateTime && startTime) {
                    const ok = /^\d{1,2}:\d{2}$/.test((startTime.value || "").trim());
                    lateTime.disabled = !ok;
                }
                recomputeDuration();
            }
            lastOff = off;
        }
        cb.addEventListener("change", refresh);
        refresh();
    }

    function fields() {
        return {
            startDate: $('input.tnmt-date-trigger[name="starting_time_0"]'),
            startTime: $('input.tnmt-time-input[name="starting_time_1"]'),
            lateDate: $('input.tnmt-date-trigger[name="late_reg_at_0"]'),
            lateTime: $('input.tnmt-time-input[name="late_reg_at_1"]'),
            duration: $('input[data-tnmt-duration="1"]'),
        };
    }

    function recomputeDuration() {
        const f = fields();
        if (!f.duration) return;
        if (!isLateAvailable()) {
            f.duration.value = "";
            return;
        }
        const start = parseDdmmyyyyHhmm(f.startDate && f.startDate.value, f.startTime && f.startTime.value);
        const late = parseDdmmyyyyHhmm(f.lateDate && f.lateDate.value, f.lateTime && f.lateTime.value);
        if (!start || !late) {
            f.duration.value = "";
            return;
        }
        const diffMin = (late.getTime() - start.getTime()) / 60000;
        f.duration.value = diffMin < 0 ? "" : formatDuration(diffMin);
    }

    function bindDurationRecalc() {
        const f = fields();
        [f.startDate, f.startTime, f.lateDate, f.lateTime].forEach(function (el) {
            if (!el) return;
            el.addEventListener("input", recomputeDuration);
            el.addEventListener("change", recomputeDuration);
        });
    }

    /** Maintain the invariant `late >= start`. When starting_time moves
     *  forward past the current late_reg_at, snap late forward to match
     *  so the form is never in an invalid state. Only fires when the
     *  late-reg checkbox is on; otherwise late is pinned server-side
     *  to equal start at save anyway. */
    function bindStartChangeSnaps() {
        const f = fields();
        if (!f.startDate || !f.startTime || !f.lateDate || !f.lateTime) return;
        function snapIfInvalid() {
            if (!isLateAvailable()) return;
            const start = parseDdmmyyyyHhmm(f.startDate.value, f.startTime.value);
            if (!start) return;
            const late = parseDdmmyyyyHhmm(f.lateDate.value, f.lateTime.value);
            if (!late || late >= start) return;
            f.lateDate.value = f.startDate.value;
            f.lateTime.value = f.startTime.value;
            f.lateDate.dispatchEvent(new Event("input", { bubbles: true }));
            f.lateDate.dispatchEvent(new Event("change", { bubbles: true }));
            f.lateTime.dispatchEvent(new Event("input", { bubbles: true }));
            f.lateTime.dispatchEvent(new Event("change", { bubbles: true }));
        }
        [f.startDate, f.startTime].forEach(function (el) {
            el.addEventListener("input", snapIfInvalid);
            el.addEventListener("change", snapIfInvalid);
        });
    }

    function clientSideOrderingValidation() {
        const f = fields();
        const submit = function (e) {
            const start = parseDdmmyyyyHhmm(f.startDate && f.startDate.value, f.startTime && f.startTime.value);
            const late = parseDdmmyyyyHhmm(f.lateDate && f.lateDate.value, f.lateTime && f.lateTime.value);
            if (start && late && late < start) {
                e.preventDefault();
                e.stopPropagation();
                f.lateTime && f.lateTime.focus();
                window.alert(
                    "Late registration cannot close before the tournament starts."
                );
            }
        };
        const realForm = document.getElementById("tournament_form");
        if (realForm) realForm.addEventListener("submit", submit);
    }

    /** Mask out days strictly earlier than the starting date in the
     *  late-reg calendar popup (they remain visible but become a plain
     *  greyed-out span with no click handler). */
    function bindDatePickerGating() {
        const ds = window.DateTimeShortcuts;
        if (!ds) return;
        $$("input.tnmt-date-trigger").forEach(function (dateInput) {
            if (dateInput.name !== "late_reg_at_0") return;
            const num = ds.calendarInputs.indexOf(dateInput);
            if (num < 0) return;
            const grid = document.getElementById("calendarin" + num);
            if (!grid) return;

            function applyMask() {
                $$("span.tnmt-day-disabled", grid).forEach(function (s) {
                    const a = document.createElement("a");
                    a.href = "#";
                    a.textContent = s.textContent;
                    s.parentNode.replaceChild(a, s);
                });
                const f = fields();
                const start = parseDdmmyyyy(f.startDate && f.startDate.value);
                if (!start) return;
                const cal = ds.calendars[num];
                if (!cal) return;
                const month = cal.currentMonth;
                const year = cal.currentYear;
                $$("td > a", grid).forEach(function (a) {
                    const day = parseInt(a.textContent, 10);
                    if (!day) return;
                    const cellDate = new Date(year, month - 1, day);
                    if (cellDate < start) {
                        const span = document.createElement("span");
                        span.textContent = a.textContent;
                        span.className = "tnmt-day-disabled";
                        a.parentNode.replaceChild(span, a);
                    }
                });
            }
            new MutationObserver(applyMask).observe(grid, { childList: true, subtree: true });
        });
    }

    function bindGlobalDismissers() {
        const tzSelect = document.getElementById("id_timezone");
        if (tzSelect) {
            ["mousedown", "focus"].forEach(function (evt) {
                tzSelect.addEventListener(evt, function () {
                    closeTimePopup();
                    closeOtherPickers();
                });
            });
        }
    }

    /** Clamp `late_reg_level` to its model minimum (1) on every edit so
     *  the user can't even momentarily type 0 — `min="1"` on the widget
     *  alone only blocks at submit time. */
    function clampLateRegLevel() {
        const inp = document.getElementById("id_late_reg_level");
        if (!inp) return;
        function clamp() {
            if (inp.disabled) return;
            const v = inp.value.trim();
            if (v === "") return;
            const n = parseInt(v, 10);
            if (!isNaN(n) && n < 1) inp.value = "1";
        }
        inp.addEventListener("input", clamp);
        inp.addEventListener("change", clamp);
        inp.addEventListener("blur", clamp);
    }

    function init() {
        rewireDateTimeShortcuts();
        applyDefaults();
        gateLateRegTime();
        bindLateRegAvailableToggle();
        bindDurationRecalc();
        bindStartChangeSnaps();
        recomputeDuration();
        clientSideOrderingValidation();
        bindGlobalDismissers();
        bindDatePickerGating();
        clampLateRegLevel();
    }

    // Django's DateTimeShortcuts.init also runs on window.load; we register
    // afterwards so the shortcut spans already exist when we rewire them.
    window.addEventListener("load", init);
})();

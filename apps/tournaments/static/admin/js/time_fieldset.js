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

    function parseHhmm(s) {
        const m = /^(\d{1,2}):(\d{2})$/.exec((s || "").trim());
        if (!m) return null;
        return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);  // minutes since midnight
    }

    /* --- recurrence mode (date hidden for recurring tournaments) -------- */

    function isRecurringMode() {
        const sel = document.querySelector('select[data-tnmt-periodicity="1"]');
        if (!sel) return false;
        const opt = sel.options[sel.selectedIndex];
        if (!opt) return false;
        const raw = opt.getAttribute("data-interval-seconds");
        return raw !== null && raw !== "" && parseInt(raw, 10) > 0;
    }

    /** For a recurring tournament only the time-of-day matters, so hide and
     *  disable the DATE inputs (disabled => not submitted; the server
     *  synthesizes the anchor date). One-off shows them as before. */
    function applyRecurrenceMode() {
        const rec = isRecurringMode();
        [["starting_time_0", false], ["late_reg_at_0", true]].forEach(function (pair) {
            const name = pair[0], isLate = pair[1];
            const dateInput = $('input.tnmt-date-trigger[name="' + name + '"]');
            if (!dateInput) return;
            const span = shortcutsAfter(dateInput);
            dateInput.style.display = rec ? "none" : "";
            if (span) span.style.display = rec ? "none" : "";
            dateInput.disabled = rec || (isLate && !isLateAvailable());
        });
        recomputeDuration();
    }

    function bindRecurrenceMode() {
        const sel = document.querySelector('select[data-tnmt-periodicity="1"]');
        if (sel) sel.addEventListener("change", applyRecurrenceMode);
        applyRecurrenceMode();
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
            const col = cell.parentNode;
            const kind = col.dataset.kind;
            const v = cell.dataset.value;
            const m = (_activeTimeInput.value || "").match(/^(\d{1,2}):(\d{2})$/);
            let hh = m ? pad(parseInt(m[1], 10)) : "00";
            let mm = m ? m[2] : "00";
            if (kind === "h") hh = v; else mm = v;
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

    function refreshTimePopupDisabled() {
        const popup = _timePopup;
        if (!popup) return;
        // Every hour/minute cell is always selectable, regardless of
        // one-off vs recurring or the starting time. The server validates
        // the late-reg/start relationship and wraps past midnight for
        // recurring tournaments, so the picker imposes no restriction here.
        $$(".tnmt-time-cell", popup).forEach(function (c) {
            c.classList.remove("tnmt-time-cell-disabled");
        });
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
        if (isRecurringMode()) {
            // Date is hidden — derive from the two times; late ≤ start ⇒ next day.
            const st = parseHhmm(f.startTime && f.startTime.value);
            const lt = parseHhmm(f.lateTime && f.lateTime.value);
            if (st == null || lt == null) {
                f.duration.value = "";
                return;
            }
            let diffMin = lt - st;
            if (diffMin <= 0) diffMin += 24 * 60;
            f.duration.value = formatDuration(diffMin);
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

    /** In the late-reg calendar, grey out and disable any day strictly
     *  earlier than the starting date so the editor literally can't
     *  pick a late-reg before the tournament starts. Pure class toggling
     *  on existing `<a>` cells (no node swapping, no MutationObserver),
     *  invoked only on explicit triggers — opens + month navigation. */
    function bindDatePickerGating() {
        const ds = window.DateTimeShortcuts;
        if (!ds) return;
        $$("input.tnmt-date-trigger").forEach(function (dateInput) {
            if (dateInput.name !== "late_reg_at_0") return;
            const num = ds.calendarInputs.indexOf(dateInput);
            if (num < 0) return;
            const box = document.getElementById("calendarbox" + num);
            const grid = document.getElementById("calendarin" + num);
            if (!box || !grid) return;

            function startDay() {
                const f = fields();
                const s = parseDdmmyyyy(f.startDate && f.startDate.value);
                if (!s) return null;
                return new Date(s.getFullYear(), s.getMonth(), s.getDate());
            }

            function applyVisual() {
                const start = startDay();
                const cal = ds.calendars[num];
                if (!cal) return;
                const month = cal.currentMonth;
                const year = cal.currentYear;
                $$("td > a", grid).forEach(function (a) {
                    const day = parseInt(a.textContent, 10);
                    if (!day) return;
                    const cellDate = new Date(year, month - 1, day);
                    if (start && cellDate < start) {
                        a.classList.add("tnmt-day-disabled");
                    } else {
                        a.classList.remove("tnmt-day-disabled");
                    }
                });
            }

            // Initial open: piggy-back on the date input click handler;
            // the calendar's grid is drawn synchronously, so a microtask
            // delay is enough.
            dateInput.addEventListener("click", function () {
                setTimeout(applyVisual, 0);
            });
            // Month navigation: prev/next-month links inside the
            // calendarbox header redraw the grid; re-apply after.
            box.addEventListener("click", function (e) {
                const link = e.target.closest("a");
                if (!link) return;
                if (link.closest(".calendarnav-previous, .calendarnav-next")) {
                    setTimeout(applyVisual, 0);
                }
            });
        });
    }

    /** Django's calendar callback sets `input.value = ...` without
     *  dispatching `input`/`change`, so our duration recompute (and the
     *  start→late snap) never see the new date. Wrap each calendar's
     *  callback to fire the events that downstream listeners expect. */
    function patchCalendarCallbacks() {
        const ds = window.DateTimeShortcuts;
        if (!ds || !ds.calendars) return;
        ds.calendars.forEach(function (cal, num) {
            if (!cal || cal._tnmtPatched) return;
            cal._tnmtPatched = true;
            const orig = cal.callback;
            cal.callback = function (y, m, d) {
                if (typeof orig === "function") orig(y, m, d);
                const inp = ds.calendarInputs[num];
                if (inp) {
                    inp.dispatchEvent(new Event("input", { bubbles: true }));
                    inp.dispatchEvent(new Event("change", { bubbles: true }));
                }
            };
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

    /** Clamp integer fields to their HTML `min`/`max` on every edit so
     *  out-of-range values can't even be typed — `min`/`max` on the
     *  widget alone only block at submit time. Respects the per-field
     *  attrs we set in `TournamentAdminForm.__init__`. */
    function clampBoundedIntFields() {
        const ids = [
            "id_late_reg_level",
            "id_blind_interval_minutes",
            "id_break_minutes",
            "id_players_per_table",
            "id_players_at_final_table",
            "id_min_players",
            "id_max_players",
            "id_starting_stack",
            "id_starting_stack_bb",
        ];
        ids.forEach(function (id) {
            const inp = document.getElementById(id);
            if (!inp) return;
            function clamp() {
                if (inp.disabled) return;
                const v = inp.value.trim();
                if (v === "") return;
                const n = parseInt(v, 10);
                if (isNaN(n)) return;
                // Read min/max on each call — they may be dynamically
                // updated by other handlers (min_players ↔ max_players
                // coupling).
                const lo = inp.min !== "" ? parseInt(inp.min, 10) : null;
                const hi = inp.max !== "" ? parseInt(inp.max, 10) : null;
                if (lo !== null && n < lo) inp.value = String(lo);
                else if (hi !== null && n > hi) inp.value = String(hi);
            }
            inp.addEventListener("input", clamp);
            inp.addEventListener("change", clamp);
            inp.addEventListener("blur", clamp);
        });
    }

    /** Maintain `min_players <= max_players` by snapping the *other*
     *  field whenever one is edited. We deliberately do NOT couple the
     *  HTML `min`/`max` between the pair — that would block the spinner
     *  from crossing the boundary. Instead, dragging `max` below `min`
     *  pulls `min` down to match (and vice versa). The absolute floor
     *  of 2 (set by the form widget) still applies. */
    function bindMinMaxPlayersCoupling() {
        const minInp = document.getElementById("id_min_players");
        const maxInp = document.getElementById("id_max_players");
        if (!minInp || !maxInp) return;

        function syncFromMin() {
            const minVal = parseInt(minInp.value, 10);
            if (isNaN(minVal)) return;
            const maxVal = parseInt(maxInp.value, 10);
            if (!isNaN(maxVal) && maxVal < minVal) {
                maxInp.value = String(minVal);
            }
        }
        function syncFromMax() {
            const maxVal = parseInt(maxInp.value, 10);
            if (isNaN(maxVal)) return;
            const minVal = parseInt(minInp.value, 10);
            if (!isNaN(minVal) && minVal > maxVal) {
                minInp.value = String(maxVal);
            }
        }

        ["input", "change", "blur"].forEach(function (evt) {
            minInp.addEventListener(evt, syncFromMin);
            maxInp.addEventListener(evt, syncFromMax);
        });
        syncFromMin();
        syncFromMax();
    }

    function init() {
        rewireDateTimeShortcuts();
        patchCalendarCallbacks();
        applyDefaults();
        gateLateRegTime();
        bindLateRegAvailableToggle();
        bindRecurrenceMode();
        bindDurationRecalc();
        bindStartChangeSnaps();
        recomputeDuration();
        bindGlobalDismissers();
        bindDatePickerGating();
        clampBoundedIntFields();
        bindMinMaxPlayersCoupling();
    }

    // Django's DateTimeShortcuts.init also runs on window.load; we register
    // afterwards so the shortcut spans already exist when we rewire them.
    window.addEventListener("load", init);
})();

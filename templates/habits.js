function isHabitScheduledForDate(habit, dateObj) {
    const pattern = habit.repeat_pattern || {};
    const type = habit.repeat_type || pattern.type || 'weekly';
    const dateKey = toLocalISODate(dateObj);

    if (type === 'custom') {
        const customDates = Array.isArray(pattern.dates) ? pattern.dates : [];
        const customWeeks = pattern.weeks || {};
        if (customDates.length) return customDates.includes(dateKey);
        return Object.values(customWeeks).some((entries) => Array.isArray(entries) && entries.some((entry) => {
            const targetWeekday = Number(entry.weekday || entry.day || 0);
            if (!targetWeekday) return false;
            return dateObj.getDay() === (targetWeekday === 7 ? 0 : targetWeekday);
        }));
    }

    const year = dateObj.getFullYear();
    const weekday = dateObj.getDay() === 0 ? 7 : dateObj.getDay();
    const month = dateObj.getMonth() + 1;
    const years = pattern.years;
    const months = pattern.months || Array.from({ length: 12 }, (_, index) => index + 1);
    const weekdays = pattern.weekdays || Array.from({ length: 7 }, (_, index) => index + 1);

    const yearMatches = !years || !years.length || years.includes(year);
    return yearMatches && months.includes(month) && weekdays.includes(weekday);
}

function isHabitCompletedOnDate(habit, dateISO) {
    const status = habit.logs && habit.logs[dateISO];
    return status === 'done' || status === 'complete' || status === 'completed';
}

function getHabitDateTime(timeString, baseDate = new Date()) {
    const [hours, minutes] = (timeString || '00:00').split(':').map(Number);

    const date = new Date(baseDate);
    date.setHours(hours || 0, minutes || 0, 0, 0);

    return date;
}


function getProHabitState(habit, todayISO) {
    const now = new Date();

    const startTime = getHabitDateTime(habit.start_time, now);
    const endTime = getHabitDateTime(habit.end_time, now);

    // Ready window:
    // habit မစခင် 15 min → habit စပြီး 15 min အထိ
    const readyStart = new Date(startTime.getTime() - 15 * 60 * 1000);
    const readyEnd = new Date(startTime.getTime() + 15 * 60 * 1000);

    // Complete window:
    // habit ပြီးခါနီး 15 min → habit ပြီးပြီး 15 min အထိ
    const completeStart = new Date(endTime.getTime() - 15 * 60 * 1000);
    const completeEnd = new Date(endTime.getTime() + 15 * 60 * 1000);

    // ဒီနေ့ရဲ့ log status
    const todayStatus = habit.logs && habit.logs[todayISO];

    // --------------------------------
    // CASE 1: Already completed
    // --------------------------------
    if (
        todayStatus === 'done' ||
        todayStatus === 'complete' ||
        todayStatus === 'completed'
    ) {
        return {
            state: 'done',
            text: 'Done',
            disabled: true
        };
    }

    // --------------------------------
    // CASE 2: User already clicked Ready (status = 'pending')
    // --------------------------------
    if (todayStatus === 'pending') {

        // Complete window
        if (now >= completeStart && now <= completeEnd) {
            return {
                state: 'complete',
                text: 'Complete',
                disabled: false
            };
        }

        // Complete window ကျော်သွားပြီ — Complete မနှိပ်ခဲ့
        if (now > completeEnd) {
            return {
                state: 'uncomplete',
                text: 'Uncomplete',
                disabled: true
            };
        }

        // Complete time မရောက်သေး
        return {
            state: 'pending',
            text: 'Pending',
            disabled: true
        };
    }

    // --------------------------------
    // No status yet — Ready window ကို အခြေခံပြီး branch ခွဲမယ်
    // (အောက်က case 3 order အတိုင်း — Coming soon ကို အရင်စစ်ရပါမယ်,
    // Ready window မစသေးရင် "Ready" ပြမသွားရအောင်)
    // --------------------------------

    // CASE 3: Ready window မရောက်သေး — "Coming soon"
    if (now < readyStart) {
        return {
            state: 'coming_soon',
            text: 'Coming soon',
            disabled: true
        };
    }

    // CASE 4: Ready window ထဲ
    if (now >= readyStart && now <= readyEnd) {
        return {
            state: 'ready',
            text: 'Ready',
            disabled: false
        };
    }

    // CASE 5: Ready window ကျော်သွားပြီ — User က Ready မနှိပ်ခဲ့
    return {
        state: 'uncomplete',
        text: 'Uncomplete',
        disabled: true
    };
}


let proHabitRefreshInterval = null;

function startProHabitAutoRefresh(habits) {
    // အရင် interval ရှိရင် ဖျက်
    if (proHabitRefreshInterval) {
        clearInterval(proHabitRefreshInterval);
    }

    // 1 မိနစ်တစ်ကြိမ် state ပြန်စစ်
    proHabitRefreshInterval = setInterval(() => {
        renderTodayHabits(habits);
    }, 60 * 1000);
}

function renderTodayHabits(habits) {
    const listEl = $('#todayHabitsList');
    const proListEl = $('#todayHabitsListPro');

    const todayISO = getTodayISO();
    const todayDate = new Date();

    const scheduled = habits.filter((habit) => isHabitScheduledForDate(habit, todayDate));

    if (listEl.length) {
        if (!scheduled.length) {
            listEl.html('<li><div><span>No habits scheduled today.</span></div></li>');
        } else {
            listEl.empty();
            scheduled.forEach((habit) => {
                const checkboxId = `habit-${habit.id}`;
                const checked = isHabitCompletedOnDate(habit, todayISO);
                const item = $(
                    '<li>' +
                    '  <div>' +
                    '    <input id="' + checkboxId + '" type="checkbox" class="habit-check" data-habit-id="' + habit.id + '" ' + (checked ? 'checked' : '') + '>' +
                    '    <span>' + (habit.habit_name || 'Habit') + '</span>' +
                    '  </div>' +
                    '  <label>' + (habit.start_time || '00:00') + ' to ' + (habit.end_time || '00:00') + '</label>' +
                    '  <button type="button" class="delete-habit-btn" data-habit-id="' + habit.id + '"><i class="fa-solid fa-trash"></i></button>' +
                    '</li>'
                );

                item.find('.delete-habit-btn').on('click', function () {
                    deleteHabitFromApi($(this).data('habitId'));
                });

                item.find('.habit-check').on('change', function () {
                    const isChecked = $(this).is(':checked');
                    const habitId = Number($(this).data('habitId'));
                    fetch('/api/habit/log', {
                        method: 'POST',
                        credentials: 'include',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            habit_id: habitId,
                            date: todayISO,
                            status: isChecked ? 'done' : 'ready',
                            completed: isChecked
                        })
                    }).then((response) => {
                        if (response.ok) return loadData();
                        return response.json().then((body) => {
                            alert(body.error || 'Unable to update habit status.');
                        });
                    }).catch(() => alert('Unable to update habit status.'));
                });

                listEl.append(item);
            });
        }
    }

    if (proListEl.length) {
        proListEl.find('li.habit-row, li.habit-empty').remove();
        if (!scheduled.length) {
            proListEl.append('<li class="habit-empty"><div><span>No habits scheduled today.</span></div></li>');
        } else {
            // -----------------------------------------------------------
            // Step 1 + Step 2: state ကို အရင်တွက်ပြီး, priority group အလိုက်
            // sort လုပ်မယ် — group တစ်ခုချင်းစီအတွင်းမှာ start_time
            // chronological order ကို base sort အနေနဲ့ ဆက်သုံးမယ်.
            //
            // Priority 0 (Top)    : ready / pending / complete — active flow ထဲရှိနေ
            // Priority 1 (Middle) : coming_soon / done
            // Priority 2 (Bottom) : uncomplete — Case2 (ready မနှိပ်ခဲ့) နှင့်
            //                       Case3 (complete မနှိပ်ခဲ့) နှစ်ခုစလုံး ဒီ state
            //                       တစ်ခုတည်းကို share နေတယ်.
            // -----------------------------------------------------------
            const priorityOf = (state) => {
                if (state === 'ready' || state === 'pending' || state === 'complete') return 0; // Top1
                if (state === 'coming_soon') return 1;                                           // Top2
                if (state === 'done') return 2;                                                  // Top3
                return 3; // uncomplete                                                          // Top4
            };

            const habitsWithState = scheduled.map((habit) => ({
                habit,
                habitState: getProHabitState(habit, todayISO)
            }));

            habitsWithState.sort((a, b) => {
                const priorityDiff = priorityOf(a.habitState.state) - priorityOf(b.habitState.state);
                if (priorityDiff !== 0) return priorityDiff;
                // Group တူတူထဲမှာ start_time (HH:MM string) အလိုက် chronological sort
                return (a.habit.start_time || '00:00').localeCompare(b.habit.start_time || '00:00');
            });

            habitsWithState.forEach(({ habit, habitState }) => {
                const row = $(
                    '<li class="habit-row">' +
                    '  <div>' +
                    '    <h2 style="font-size: 1.2em;">' + (habit.habit_name || 'Habit') + '</h2>' +
                    '    <span style="font-size: .7em;">' + (habit.repeat_type || 'weekly') + '</span>' +
                    '  </div>' +
                    '  <span>' + (habit.start_time || '00:00') + '</span>' +
                    '  <span>' + (habit.end_time || '00:00') + '</span>' +
                    '  <div style="display: flex; gap: 30px; align-items: center; justify-content: space-between;">' +
                    '    <button type="button" class="pro_habit_btn" data-habit-id="' +
                    habit.id +
                    '" data-state="' +
                    habitState.state +
                    '"' +
                    (habitState.disabled ? ' disabled' : '') +
                    '>' +
                    habitState.text +
                    '</button>' +
                    '    <button type="button" class="pro_habit_delete_btn" data-habit-id="' +
                    habit.id +
                    '">' +
                    '<i class="fa-solid fa-trash"></i>' +
                    '</button>' +
                    '  </div>' +
                    '</li>'
                );

                row.find('.pro_habit_btn').on('click', function () {
                    const button = $(this);
                    const habitId = Number(button.data('habitId'));
                    const state = button.data('state');

                    // --------------------------------
                    // READY -> PENDING
                    // --------------------------------
                    if (state === 'ready') {
                        fetch('/api/habit/log', {
                            method: 'POST',
                            credentials: 'include',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                habit_id: habitId,
                                date: todayISO,
                                status: 'pending',
                                completed: false
                            })
                        })
                            .then((response) => {
                                if (response.ok) {
                                    return loadData();
                                }

                                return response.json().then((body) => {
                                    alert(body.error || 'Unable to start habit.');
                                });
                            })
                            .catch(() => {
                                alert('Unable to start habit.');
                            });

                        return;
                    }

                    // --------------------------------
                    // COMPLETE -> DONE
                    // --------------------------------
                    if (state === 'complete') {
                        fetch('/api/habit/log', {
                            method: 'POST',
                            credentials: 'include',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                habit_id: habitId,
                                date: todayISO,
                                status: 'done',
                                completed: true
                            })
                        })
                            .then((response) => {
                                if (response.ok) {
                                    return loadData();
                                }

                                return response.json().then((body) => {
                                    alert(body.error || 'Unable to complete habit.');
                                });
                            })
                            .catch(() => {
                                alert('Unable to complete habit.');
                            });

                        return;
                    }
                });

                row.find('.pro_habit_delete_btn').on('click', function () {
                    deleteHabitFromApi(Number($(this).data('habitId')));
                });

                proListEl.append(row);
            });
        }
    }
}


function deleteHabitFromApi(habitId) {
    if (!window.confirm('Delete this habit?')) return;

    fetch('/api/habit/delete/' + habitId, {
        method: 'DELETE',
        credentials: 'include'
    }).then((response) => {
        if (!response.ok) {
            return response.json().then((body) => Promise.reject(new Error(body.error || 'Delete failed.')));
        }
        loadData();
    }).catch((error) => {
        alert(error.message || 'Unable to delete habit.');
    });
}

function buildWeeklyPatternFromForm(checkGroupSelector, monthGroupSelector, yearSelector) {
    const months = $(monthGroupSelector + ' input[type="checkbox"]:checked').map(function () {
        const key = this.id.replace(/2$/, '');
        return monthLookup[key] || null;
    }).get().filter(Boolean);

    const weekdays = $(checkGroupSelector + ' input[type="checkbox"]:checked').map(function () {
        const key = this.id.replace(/2$/, '');
        return weekdayLookup[key] || null;
    }).get().filter(Boolean);

    const year = Number($(yearSelector).val()) || new Date().getFullYear();

    return {
        type: 'weekly',
        years: [year],
        months: months.length ? months : Array.from({ length: 12 }, (_, index) => index + 1),
        weekdays: weekdays.length ? weekdays : Array.from({ length: 7 }, (_, index) => index + 1)
    };
}

function submitHabitForm(options) {
    const { nameSelector, startSelector, endSelector, dateSelector, repeatType, patternBuilder, resetFields } = options;
    const name = $(nameSelector).val().trim();
    const startTime = $(startSelector).val();
    const endTime = $(endSelector).val();

    if (!name || !startTime || !endTime) {
        alert('Habit name, start time, and end time are required.');
        return;
    }

    if (repeatType === 'custom' && !$(dateSelector).val()) {
        alert('Please pick a date for the custom-schedule habit.');
        return;
    }

    const payload = {
        habit_name: name,
        start_time: startTime,
        end_time: endTime,
        repeat_type: repeatType,
        repeat_pattern: patternBuilder()
    };

    fetch('/api/habit/create', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).then((response) => {
        if (!response.ok) {
            return response.json().then((body) => Promise.reject(new Error(body.error || 'Habit creation failed.')));
        }
        resetFields();
        loadData();
    }).catch((error) => {
        alert(error.message || 'Unable to create habit.');
    });
}

$(document).ready(function () {
    $('#normal_weekly_habit_submit').on('click', function () {
        submitHabitForm({
            nameSelector: '#normal_weekly_habit_name',
            startSelector: '#normal_weekly_start_time',
            endSelector: '#normal_weekly_end_time',
            repeatType: 'weekly',
            patternBuilder: function () {
                return buildWeeklyPatternFromForm('.m_b_left .m_b_l_week', '.m_b_left .m_b_l_months');
            },
            resetFields: function () {
                $('#normal_weekly_habit_name').val('');
                $('#normal_weekly_start_time').val('');
                $('#normal_weekly_end_time').val('');
                $('.m_b_left .m_b_l_months input[type="checkbox"]').prop('checked', false);
                $('.m_b_left .m_b_l_week input[type="checkbox"]').prop('checked', false);
            }
        });
    });

    $('#normal_custom_habit_submit').on('click', function () {
        submitHabitForm({
            nameSelector: '#normal_custom_habit_name',
            startSelector: '#normal_custom_start_time',
            endSelector: '#normal_custom_end_time',
            dateSelector: '#normal_custom_habit_date',
            repeatType: 'custom',
            patternBuilder: function () {
                const dateValue = $('.m_b_right .select input[type="date"]').val();
                return { type: 'custom', dates: dateValue ? [dateValue] : [] };
            },
            resetFields: function () {
                $('#normal_custom_habit_name').val('');
                $('#normal_custom_start_time').val('');
                $('#normal_custom_end_time').val('');
                $('.m_b_right .select input[type="date"]').val('');
            }
        });
    });

    $('#pro_weekly_habit_submit').on('click', function () {
        submitHabitForm({
            nameSelector: '#pro_weekly_habit_name',
            startSelector: '#pro_weekly_start_time',
            endSelector: '#pro_weekly_end_time',
            repeatType: 'weekly',
            patternBuilder: function () {
                return buildWeeklyPatternFromForm('.pro_habit_page .m_b_l_week', '.pro_habit_page .m_b_l_months', '#pro_weekly_habit_year');
            },
            resetFields: function () {
                $('#pro_weekly_habit_name').val('');
                $('#pro_weekly_start_time').val('');
                $('#pro_weekly_end_time').val('');
                $('#pro_weekly_habit_year').val(new Date().getFullYear());
                $('.pro_habit_page .m_b_l_months input[type="checkbox"]').prop('checked', false);
                $('.pro_habit_page .m_b_l_week input[type="checkbox"]').prop('checked', false);
            }
        });
    });

    $('#pro_custom_habit_submit').on('click', function () {
        submitHabitForm({
            nameSelector: '#pro_custom_habit_name',
            startSelector: '#pro_custom_start_time',
            endSelector: '#pro_custom_end_time',
            dateSelector: '#pro_custom_habit_date',
            repeatType: 'custom',
            patternBuilder: function () {
                const dateValue = $('.pro_habit_page .m_b_right .select input[type="date"]').val();
                return { type: 'custom', dates: dateValue ? [dateValue] : [] };
            },
            resetFields: function () {
                $('#pro_custom_habit_name').val('');
                $('#pro_custom_start_time').val('');
                $('#pro_custom_end_time').val('');
                $('.pro_habit_page .m_b_right .select input[type="date"]').val('');
            }
        });
    });
});

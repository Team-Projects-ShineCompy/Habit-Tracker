const ADMIN_USER_ID = window.ADMIN_TARGET_USER_ID;
let currentCalendarDate = new Date();

function toLocalISODate(dateObj) {
    const year = dateObj.getFullYear();
    const month = String(dateObj.getMonth() + 1).padStart(2, '0');
    const day = String(dateObj.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function isHabitScheduledForDate(habit, dateObj) {
    const pattern = habit.repeat_pattern || {};
    const type = habit.repeat_type || pattern.type || 'weekly';
    const dateKey = toLocalISODate(dateObj);

    if (type === 'custom') {
        const customDates = Array.isArray(pattern.dates) ? pattern.dates : [];
        if (customDates.length) return customDates.includes(dateKey);
        return false;
    }

    const year = dateObj.getFullYear();
    const weekday = dateObj.getDay() === 0 ? 7 : dateObj.getDay();
    const month = dateObj.getMonth() + 1;
    const years = pattern.years;
    const months = pattern.months || Array.from({ length: 12 }, (_, i) => i + 1);
    const weekdays = pattern.weekdays || Array.from({ length: 7 }, (_, i) => i + 1);

    const yearMatches = !years || !years.length || years.includes(year);
    return yearMatches && months.includes(month) && weekdays.includes(weekday);
}

function getHabitDateTime(timeString, baseDate = new Date()) {
    const [hours, minutes] = (timeString || '00:00').split(':').map(Number);
    const date = new Date(baseDate);
    date.setHours(hours || 0, minutes || 0, 0, 0);
    return date;
}

function getHabitTodayStatus(habit, todayISO) {
    const status = habit.logs && habit.logs[todayISO];
    if (status === 'done' || status === 'complete' || status === 'completed') return { state: 'done', text: 'Done' };
    if (status === 'pending') return { state: 'pending', text: 'Pending' };

    const now = new Date();
    const startTime = getHabitDateTime(habit.start_time, now);
    const readyStart = new Date(startTime.getTime() - 15 * 60 * 1000);
    const readyEnd = new Date(startTime.getTime() + 15 * 60 * 1000);

    if (now < readyStart) return { state: 'coming_soon', text: 'Coming soon' };
    if (now >= readyStart && now <= readyEnd) return { state: 'ready', text: 'Ready' };
    return { state: 'uncomplete', text: 'Not started' };
}

function renderAdminTodayHabits(habits) {
    const todayISO = toLocalISODate(new Date());
    const scheduled = habits.filter((habit) => isHabitScheduledForDate(habit, new Date()));
    const listEl = $('#adminTodayHabitsList');
    listEl.empty();

    if (!scheduled.length) {
        listEl.html('<li><span>No habits scheduled today.</span></li>');
        return;
    }

    scheduled.forEach((habit) => {
        const status = getHabitTodayStatus(habit, todayISO);
        listEl.append(
            '<li>' +
            '  <span>' + (habit.habit_name || 'Habit') + ' <small style="opacity:.6;">(' + (habit.start_time || '') + ' - ' + (habit.end_time || '') + ')</small></span>' +
            '  <span class="status_tag status_' + status.state + '">' + status.text + '</span>' +
            '</li>'
        );
    });
}

function renderStatisticsTable(habitBreakdown) {
    const tableBody = $('#lists_checked_completed_missed');
    const rows = Object.entries(habitBreakdown || {});

    if (!rows.length) {
        tableBody.html('<li><p>No habit statistics for this month.</p></li>');
        return;
    }

    const html = rows.map(([habitName, stats]) => {
        const totalTimeMin = Number(stats.total_time_min || 0);
        const completionRate = Number(stats.completion_rate || 0);
        const formattedMinutes = Number.isInteger(totalTimeMin) ? totalTimeMin : totalTimeMin.toFixed(1);
        const formattedRate = Number.isInteger(completionRate) ? completionRate : completionRate.toFixed(1);
        return '<li><p>' + habitName + '</p><span>' + formattedMinutes + ' min</span><span>' + formattedRate + '%</span></li>';
    }).join('');

    tableBody.html(html);
}

function renderDailyChart(dailyStats) {
    const canvas = document.getElementById('rate_data');
    if (!canvas || typeof Chart === 'undefined') return;

    const sortedEntries = Object.entries(dailyStats || {}).sort(([a], [b]) => new Date(a) - new Date(b));
    const labels = sortedEntries.map(([date]) => new Date(date + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
    const values = sortedEntries.map(([, v]) => Number(v) || 0);

    if (window.adminChartInstance) window.adminChartInstance.destroy();

    const ctx = canvas.getContext('2d');
    window.adminChartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets: [{ label: 'Completion Rate (%)', data: values, borderColor: '#2dcdf5', backgroundColor: 'rgba(45, 205, 245, 0.2)', borderWidth: 2, fill: true, tension: 0.3, pointRadius: 4, pointBackgroundColor: '#eff3f4', pointBorderColor: '#2dcdf5' }] },
        options: {
            responsive: true, maintainAspectRatio: false, layout: { padding: 10 },
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => c.parsed.y + '%' } } },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.08)' }, ticks: { color: '#eff3f4', maxTicksLimit: 8 } },
                y: { min: 0, max: 100, ticks: { stepSize: 20, color: '#eff3f4' }, grid: { color: 'rgba(255,255,255,0.08)' } }
            }
        }
    });
}

function loadStatisticsForMonth(year, month) {
    $('#lists_checked_completed_missed').html('<li><p>Loading...</p></li>');

    Promise.all([
        fetch(`/api/admin/user/${ADMIN_USER_ID}/statistics/daily?year=${year}&month=${month}`, { credentials: 'include' }),
        fetch(`/api/admin/user/${ADMIN_USER_ID}/statistics/habits?year=${year}&month=${month}`, { credentials: 'include' })
    ]).then(async ([dailyRes, breakdownRes]) => {
        if (dailyRes.status === 401 || breakdownRes.status === 401) {
            window.location.href = '/admin/login';
            return;
        }
        const dailyStats = dailyRes.ok ? await dailyRes.json() : {};
        const habitBreakdown = breakdownRes.ok ? await breakdownRes.json() : {};
        renderDailyChart(dailyStats);
        renderStatisticsTable(habitBreakdown);
    }).catch(() => {
        renderDailyChart({});
        $('#lists_checked_completed_missed').html('<li><p>Unable to load data.</p></li>');
    });
}

function populateAdminCalendar() {
    currentCalendarDate = new Date();
    $('#year').text(currentCalendarDate.getFullYear());
    $('#month').text(currentCalendarDate.toLocaleString('en-US', { month: 'long' }));
    loadStatisticsForMonth(currentCalendarDate.getFullYear(), currentCalendarDate.getMonth() + 1);
}

function loadAdminUserPage() {
    fetch(`/api/admin/user/${ADMIN_USER_ID}`, { credentials: 'include' }).then(async (response) => {
        if (response.status === 401) { window.location.href = '/admin/login'; return; }
        if (!response.ok) { $('#adminUserEmail').text('User not found'); return; }
        const body = await response.json();
        $('#adminUserEmail').text(body.user.email);
    });

    Promise.all([
        fetch(`/api/admin/user/${ADMIN_USER_ID}/habits`, { credentials: 'include' }),
        fetch(`/api/admin/user/${ADMIN_USER_ID}/logs`, { credentials: 'include' }),
        fetch(`/api/admin/user/${ADMIN_USER_ID}/statistics`, { credentials: 'include' })
    ]).then(async ([habitRes, logsRes, statsRes]) => {
        const habits = habitRes.ok ? (await habitRes.json()).habits || [] : [];
        const logs = logsRes.ok ? (await logsRes.json()).logs || {} : {};
        const stats = statsRes.ok ? await statsRes.json() : {};

        habits.forEach((habit) => { habit.logs = logs[String(habit.id)] || {}; });

        renderAdminTodayHabits(habits);
        $('#adminStreakLabel').text(`${stats.current_streak || 0} days`);
    });

    populateAdminCalendar();
}

$(document).ready(function () {
    fetch('/api/admin/me', { credentials: 'include' }).then((response) => {
        if (!response.ok) { window.location.href = '/admin/login'; return; }
        loadAdminUserPage();
    }).catch(() => { window.location.href = '/admin/login'; });

    $('#text_btn').click(function () {
        currentCalendarDate.setMonth(currentCalendarDate.getMonth() + 1);
        $('#year').text(currentCalendarDate.getFullYear());
        $('#month').text(currentCalendarDate.toLocaleString('en-US', { month: 'long' }));
        loadStatisticsForMonth(currentCalendarDate.getFullYear(), currentCalendarDate.getMonth() + 1);
    });

    $('#back_btn').click(function () {
        currentCalendarDate.setMonth(currentCalendarDate.getMonth() - 1);
        $('#year').text(currentCalendarDate.getFullYear());
        $('#month').text(currentCalendarDate.toLocaleString('en-US', { month: 'long' }));
        loadStatisticsForMonth(currentCalendarDate.getFullYear(), currentCalendarDate.getMonth() + 1);
    });
});

function getTodayISO() {
    return toLocalISODate(new Date());
}

function toLocalISODate(dateObj) {
    const year = dateObj.getFullYear();
    const month = String(dateObj.getMonth() + 1).padStart(2, '0');
    const day = String(dateObj.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function n_or_p() {
    const n_or_p_value = $('#n_or_p').val();

    if (n_or_p_value == 0) {
        $('.normal_right').removeClass('remove');
        $('.pro_right').addClass('remove');
        $('#main_menu_statistics').css({ display: 'none' });
        $('#body').addClass('white');
    } else {
        $('.normal_right').addClass('remove');
        $('.pro_right').removeClass('remove');
        $('#main_menu_statistics').css({ display: '' });
        $('#body').removeClass('white');
    }
}

function showHomeSummary(summary) {
    const completedToday = Number(summary.completed_today || 0);
    const scheduledToday = Number(summary.today_habits || 0);
    const missedHabitsValue = Number(summary.today_habits - summary.completed_today || 0);
    const percent = Number(summary.today_rate || 0);

    $('#completedTodayValue').text(completedToday);
    $('#todayHabitsValue').text(scheduledToday);
    $('#todayRateValue').text(`${percent}%`);

    if ($('#completedTodayValuePro').length) $('#completedTodayValuePro').text(completedToday);
    if ($('#missedHabitsValuePro').length) $('#missedHabitsValuePro').text(missedHabitsValue);
    if ($('#todayHabitsValuePro').length) $('#todayHabitsValuePro').text(scheduledToday);
    if ($('#todayRateValuePro').length) $('#todayRateValuePro').text(`${percent}%`);
}

function loadData() {
    Promise.all([
        fetch('/api/habit/list', { method: 'GET', credentials: 'include' }),
        fetch('/api/habit/logs', { method: 'GET', credentials: 'include' }),
        fetch('/api/statistics', { method: 'GET', credentials: 'include' }),
        fetch('/api/statistics/daily', { method: 'GET', credentials: 'include' }),
        fetch('/api/statistics/habits', { method: 'GET', credentials: 'include' })
    ]).then(async ([habitRes, logsRes, statsRes, dailyRes, breakdownRes]) => {
        if (habitRes.status === 401 || logsRes.status === 401 || statsRes.status === 401 || dailyRes.status === 401 || breakdownRes.status === 401) {
            window.location.href = '/login';
            return;
        }

        const habits = habitRes.ok ? (await habitRes.json()).habits || [] : [];
        const logs = logsRes.ok ? (await logsRes.json()).logs || {} : {};
        const stats = statsRes.ok ? (await statsRes.json()) : {};
        const dailyStats = dailyRes.ok ? (await dailyRes.json()) : {};
        const habitBreakdown = breakdownRes.ok ? (await breakdownRes.json()) : {};

        habits.forEach((habit) => {
            const habitId = String(habit.id);
            habit.logs = logs[habitId] || {};
        });

        const todayDate = new Date();
        const todayISO = getTodayISO();
        const scheduledToday = habits.filter((habit) => isHabitScheduledForDate(habit, todayDate));

        const completedToday = scheduledToday.filter((habit) => {
            const logStatus = habit.logs && habit.logs[todayISO];
            return logStatus === 'done' || logStatus === 'complete';
        }).length;

        showHomeSummary({
            completed_today: completedToday,
            today_habits: scheduledToday.length,
            today_rate: scheduledToday.length ? Math.round((completedToday / scheduledToday.length) * 100) : 0
        });

        renderTodayHabits(habits);
        startProHabitAutoRefresh(habits);
        $('.streak label').text(`${stats.current_streak || 0} days`);

        if (stats.completion_rate !== undefined) {
            const monthLabel = todayDate.toLocaleString('en-US', { month: 'long' });
            const yearLabel = todayDate.getFullYear();
            $('#month').text(monthLabel);
            $('#year').text(yearLabel);
        }

    }).catch(() => {
        showHomeSummary({ completed_today: 0, today_habits: 0, today_rate: 0 });
        $('#todayHabitsList').html('<li><div><span>No habits scheduled today.</span></div></li>');
        $('#lists_checked_completed_missed').html('<li><p>No API data available.</p></li>');
    });
}

$(document).ready(function () {
    n_or_p();
    populatePageCalendar();

    $('#main_menu_home').click(function () {
        const n_or_p_value = $('#n_or_p').val();
        if (n_or_p_value == 0) {
            $('.normal_home_page').removeClass('remove');
            $('.normal_habits_page').addClass('remove');
        } else {
            $('.pro_home_page').removeClass('remove');
            $('.pro_habit_page').addClass('remove');
            $('.statistics').addClass('remove');
        }
    });

    $('#main_menu_habits').click(function () {
        const n_or_p_value = $('#n_or_p').val();
        if (n_or_p_value == 0) {
            $('.normal_home_page').addClass('remove');
            $('.normal_habits_page').removeClass('remove');
        } else {
            $('.pro_home_page').addClass('remove');
            $('.pro_habit_page').removeClass('remove');
            $('.statistics').addClass('remove');
        }
    });

    $('#main_menu_statistics').click(function () {
        $('.statistics').removeClass('remove');
        $('.pro_home_page').addClass('remove');
        $('.pro_habit_page').addClass('remove');
    });

    $('#logoutBtn').on('click', function (event) {
        event.preventDefault();
        fetch('/api/logout', {
            method: 'POST',
            credentials: 'include'
        }).finally(() => {
            window.location.href = '/login';
        });
    });

    fetch('/api/me', { credentials: 'include' }).then((response) => {
        if (!response.ok) {
            window.location.href = '/login';
            return;
        }
        loadData();
    }).catch(() => {
        window.location.href = '/login';
    });
});

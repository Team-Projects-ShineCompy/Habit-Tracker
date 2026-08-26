function renderStatisticsTable(habitBreakdown) {
    const tableBody = $('#lists_checked_completed_missed');
    if (!tableBody.length) return;

    const rows = Object.entries(habitBreakdown || {});

    if (!rows.length) {
        tableBody.html('<li><p>No habit statistics yet.</p></li>');
        return;
    }

    const html = rows.map(([habitName, stats]) => {
        const totalTimeMin = Number(stats.total_time_min || 0);
        const completionRate = Number(stats.completion_rate || 0);
        const formattedMinutes = Number.isInteger(totalTimeMin) ? totalTimeMin : totalTimeMin.toFixed(1);
        const formattedRate = Number.isInteger(completionRate) ? completionRate : completionRate.toFixed(1);

        return '<li>' +
            '  <p>' + habitName + '</p>' +
            '  <span>' + formattedMinutes + ' min</span>' +
            '  <span>' + formattedRate + '%</span>' +
            '</li>';
    }).join('');

    tableBody.html(html);
}

function renderDailyChart(dailyStats) {
    const canvas = document.getElementById('rate_data');
    if (!canvas || typeof Chart === 'undefined') return;

    const sortedEntries = Object.entries(dailyStats || {}).sort(([leftDate], [rightDate]) => new Date(leftDate) - new Date(rightDate));
    const labels = sortedEntries.map(([date]) => {
        const parsed = new Date(date + 'T00:00:00');
        return parsed.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });
    const values = sortedEntries.map(([, value]) => Number(value) || 0);

    if (window.statisticsChartInstance) {
        window.statisticsChartInstance.destroy();
    }

    const ctx = canvas.getContext('2d');
    window.statisticsChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Completion Rate (%)',
                data: values,
                borderColor: '#2dcdf5',
                backgroundColor: 'rgba(45, 205, 245, 0.2)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 4,
                pointHoverRadius: 5,
                pointBackgroundColor: '#eff3f4',
                pointBorderColor: '#2dcdf5'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: 10 },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return context.parsed.y + '%';
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.08)' },
                    ticks: { color: '#eff3f4', maxTicksLimit: 8 }
                },
                y: {
                    min: 0,
                    max: 100,
                    ticks: { stepSize: 20, color: '#eff3f4' },
                    grid: { color: 'rgba(255, 255, 255, 0.08)' }
                }
            }
        }
    });
}

function renderStreak(streakValue) {
    $('.streak label').text(`${streakValue || 0} days`);
}

function loadStatisticsForMonth(year, month) {
    $('#lists_checked_completed_missed').html('<li><p>Loading...</p></li>');
    showChartLoading();

    Promise.all([
        fetch(`/api/statistics/daily?year=${year}&month=${month}`, { method: 'GET', credentials: 'include' }),
        fetch(`/api/statistics/habits?year=${year}&month=${month}`, { method: 'GET', credentials: 'include' })
    ]).then(async ([dailyRes, breakdownRes]) => {
        if (dailyRes.status === 401 || breakdownRes.status === 401) {
            window.location.href = '/login';
            return;
        }

        const dailyStats = dailyRes.ok ? await dailyRes.json() : {};
        const habitBreakdown = breakdownRes.ok ? await breakdownRes.json() : {};

        renderDailyChart(dailyStats);
        renderStatisticsTable(habitBreakdown);

    }).catch(() => {
        renderDailyChart({});
        $('#lists_checked_completed_missed').html('<li><p>No API data available.</p></li>');
    });
}

function showChartLoading() {
    const canvas = document.getElementById('rate_data');
    if (!canvas) return;
    if (window.statisticsChartInstance) {
        window.statisticsChartInstance.destroy();
        window.statisticsChartInstance = null;
    }
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.font = '14px sans-serif';
    ctx.fillStyle = '#eff3f4';
    ctx.textAlign = 'center';
    ctx.fillText('Loading...', canvas.width / 2, canvas.height / 2);
    ctx.restore();
}

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
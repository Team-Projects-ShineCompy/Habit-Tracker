let currentCalendarDate = new Date();

function populatePageCalendar() {
    currentCalendarDate = new Date();
    $('#year').text(currentCalendarDate.getFullYear());
    $('#month').text(currentCalendarDate.toLocaleString('en-US', { month: 'long' }));
    loadStatisticsForMonth(currentCalendarDate.getFullYear(), currentCalendarDate.getMonth() + 1);
}

$(document).ready(function () {
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

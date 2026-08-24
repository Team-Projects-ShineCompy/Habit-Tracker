function populatePageCalendar() {
    const calendar = new Date();
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

    $('#year').text(calendar.getFullYear());
    $('#month').text(months[calendar.getMonth()]);
}

$(document).ready(function () {
    $('#text_btn').click(function () {
        const calendar = new Date();
        calendar.setMonth(calendar.getMonth() + 1);
        $('#year').text(calendar.getFullYear());
        $('#month').text(calendar.toLocaleString('en-US', { month: 'long' }));
    });

    $('#back_btn').click(function () {
        const calendar = new Date();
        calendar.setMonth(calendar.getMonth() - 1);
        $('#year').text(calendar.getFullYear());
        $('#month').text(calendar.toLocaleString('en-US', { month: 'long' }));
    });
});
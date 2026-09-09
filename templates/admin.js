function loadAdminUsers() {
    fetch('/api/admin/users', { credentials: 'include' }).then(async (response) => {
        if (response.status === 401) {
            window.location.href = '/admin/login';
            return;
        }
        const body = await response.json();
        const users = body.users || [];
        const tbody = $('#adminUserTableBody');
        tbody.empty();

        if (!users.length) {
            tbody.html('<tr><td colspan="2">No users found.</td></tr>');
            return;
        }

        users.forEach((user) => {
            const row = $(
                '<tr>' +
                '  <td>' + user.email + '</td>' +
                '  <td>' + (user.created_at || '') + '</td>' +
                '</tr>'
            );

            row.on('click', function () {
                window.location.href = '/admin/user/' + user.id;
            });

            tbody.append(row);
        });
    }).catch(() => {
        $('#adminUserTableBody').html('<tr><td colspan="2">Unable to load users.</td></tr>');
    });
}

$(document).ready(function () {
    fetch('/api/admin/me', { credentials: 'include' }).then((response) => {
        if (!response.ok) {
            window.location.href = '/admin/login';
            return;
        }
        loadAdminUsers();
    }).catch(() => {
        window.location.href = '/admin/login';
    });

    $('#adminLogoutBtn').on('click', function () {
        fetch('/api/admin/logout', { method: 'POST', credentials: 'include' }).finally(() => {
            window.location.href = '/admin/login';
        });
    });
});

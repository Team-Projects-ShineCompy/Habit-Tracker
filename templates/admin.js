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
            tbody.html('<tr><td colspan="3">No users found.</td></tr>');
            return;
        }

        users.forEach((user) => {
            const row = $(
                '<tr>' +
                '  <td>' + user.email + '</td>' +
                '  <td>' + (user.created_at || '') + '</td>' +
                '  <td class="delete_cell"><button class="delete_user_btn"><i class="fa-solid fa-trash"></i></button></td>' +
                '</tr>'
            );

            row.on('click', function (e) {
                if ($(e.target).closest('.delete_user_btn').length) return;
                window.location.href = '/admin/user/' + user.id;
            });

            row.find('.delete_user_btn').on('click', function (e) {
                e.stopPropagation();
                if (!window.confirm('Delete user "' + user.email + '"? This will permanently remove all their habits and logs.')) return;

                fetch('/api/admin/user/' + user.id, {
                    method: 'DELETE',
                    credentials: 'include'
                }).then((response) => {
                    if (!response.ok) {
                        return response.json().then((body) => Promise.reject(new Error(body.error || 'Delete failed.')));
                    }
                    loadAdminUsers();
                }).catch((error) => {
                    alert(error.message || 'Unable to delete user.');
                });
            });

            tbody.append(row);
        });
    }).catch(() => {
        $('#adminUserTableBody').html('<tr><td colspan="3">Unable to load users.</td></tr>');
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

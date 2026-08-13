document.addEventListener('DOMContentLoaded', function () {

    var csrfToken = document.querySelector('meta[name="csrf-token"]').content;

    // ---------- Toggle buttons: Start / Finished / Contacted ----------
    document.querySelectorAll('.action-btn[data-field]').forEach(function (btn) {
        var orderBox = document.getElementById('order-' + btn.dataset.id);
        var field = btn.dataset.field;
        if (orderBox && orderBox.dataset[field] === 'true') {
            btn.classList.add('active');
        }

        btn.addEventListener('click', function () {
            var id = btn.dataset.id;
            fetch('/orders/' + id + '/toggle/' + field, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken }
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data.success) {
                        btn.classList.toggle('active', data.value);
                    }
                });
        });
    });



    // ---------- Delete order with confirmation ----------
    var deleteModal = document.getElementById('deleteModal');
    var confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
    var cancelDeleteBtn = document.getElementById('cancelDeleteBtn');
    var pendingDeleteId = null;
    var pendingDeleteBox = null;

    document.querySelectorAll('.delete-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            pendingDeleteId = btn.dataset.id;
            pendingDeleteBox = document.getElementById('order-' + pendingDeleteId);
            deleteModal.style.display = 'flex';
        });
    });

    cancelDeleteBtn.addEventListener('click', function () {
        deleteModal.style.display = 'none';
        pendingDeleteId = null;
        pendingDeleteBox = null;
    });

    deleteModal.addEventListener('click', function (e) {
        if (e.target === deleteModal) {
            deleteModal.style.display = 'none';
            pendingDeleteId = null;
            pendingDeleteBox = null;
        }
    });

    confirmDeleteBtn.addEventListener('click', function () {
        if (!pendingDeleteId) return;
        fetch('/orders/' + pendingDeleteId + '/delete', {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken }
        })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data.success && pendingDeleteBox) {
                    pendingDeleteBox.remove();
                }
                deleteModal.style.display = 'none';
                pendingDeleteId = null;
                pendingDeleteBox = null;
            });
    });

});
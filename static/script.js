document.addEventListener('DOMContentLoaded', function () {

  var csrfToken = document.querySelector('meta[name="csrf-token"]').content;

  // ---------- View as Barista / Login modal ----------
  var viewAsBaristaBtn = document.getElementById('viewAsBaristaBtn');
  var loginModal = document.getElementById('loginModal');
  var closeModalBtn = document.getElementById('closeModalBtn');

  if (viewAsBaristaBtn) {
    viewAsBaristaBtn.addEventListener('click', function () {
      loginModal.style.display = 'flex';
    });
  }

  if (closeModalBtn) {
    closeModalBtn.addEventListener('click', function () {
      loginModal.style.display = 'none';
    });
  }

  if (loginModal) {
    loginModal.addEventListener('click', function (e) {
      if (e.target === loginModal) {
        loginModal.style.display = 'none';
      }
    });
  }

  if (loginModal && window.location.search.indexOf('login_error') !== -1) {
    loginModal.style.display = 'flex';
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  // ---------- Shakin' Espresso only allowed for cold drinks ----------
  function updateColdOnlyAvailability() {
    var selected = document.querySelector('input[name="temp"]:checked');
    var isCold = !!selected && selected.value === 'Frio';

    document.querySelectorAll('input[data-cold-only="true"]').forEach(function (input) {
      var row = input.closest('.option-row');
      var isPermanentlyRemoved = row && row.classList.contains('removed-option');
      if (isPermanentlyRemoved) {
        return;
      }
      input.disabled = !isCold;
      if (!isCold) {
        input.checked = false;
      }
      if (row) {
        row.classList.toggle('option-disabled', !isCold);
      }
    });
  }

  // ---------- Americano has no milk, so milk isn't required for it ----------
  function updateMilkRequirement() {
    var selectedDrink = document.querySelector('input[name="drink"]:checked');
    var isAmericano = !!selectedDrink && selectedDrink.value === 'Americano';
    var milkGroup = document.querySelector('.option-group[data-category="milk"]');
    if (!milkGroup) return;

    milkGroup.querySelectorAll('input[name="milk"]').forEach(function (input) {
      var row = input.closest('.option-row');
      var isPermanentlyRemoved = row && row.classList.contains('removed-option');

      input.required = !isAmericano;

      if (isAmericano) {
        input.checked = false;
        if (!isPermanentlyRemoved) input.disabled = true;
        if (row) row.classList.add('option-disabled');
      } else if (!isPermanentlyRemoved) {
        input.disabled = false;
        if (row) row.classList.remove('option-disabled');
      }
    });
  }

  // ---------- Selected option turns the whole row white, not just a dot ----------
  function syncSelectedOptionStyling() {
    document.querySelectorAll('.option-row').forEach(function (row) {
      var input = row.querySelector('input');
      row.classList.toggle('selected-option', !!(input && input.checked));
    });
  }

  document.body.addEventListener('change', function (e) {
    if (!e.target.matches('.option-row input')) return;

    syncSelectedOptionStyling();

    if (e.target.name === 'temp') updateColdOnlyAvailability();
    if (e.target.name === 'drink') updateMilkRequirement();
  });

  updateColdOnlyAvailability();
  updateMilkRequirement();
  syncSelectedOptionStyling();

  if (closeModalBtn) {
    closeModalBtn.addEventListener('click', function () {
      loginModal.style.display = 'none';
    });
  }

  if (loginModal) {
    loginModal.addEventListener('click', function (e) {
      if (e.target === loginModal) {
        loginModal.style.display = 'none';
      }
    });
  }

  if (loginModal && window.location.search.indexOf('login_error') !== -1) {
    loginModal.style.display = 'flex';
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  // ---------- Shakin' Espresso only allowed for cold drinks ----------
  function updateColdOnlyAvailability() {
    var selected = document.querySelector('input[name="temp"]:checked');
    var isCold = !!selected && selected.value === 'Frio';

    document.querySelectorAll('input[data-cold-only="true"]').forEach(function (input) {
      var row = input.closest('.option-row');
      var isPermanentlyRemoved = row && row.classList.contains('removed-option');
      if (isPermanentlyRemoved) {
        return;
      }
      input.disabled = !isCold;
      if (!isCold) {
        input.checked = false;
      }
      if (row) {
        row.classList.toggle('option-disabled', !isCold);
      }
    });
  }

  // ---------- Americano has no milk, so milk isn't required for it ----------
  function updateMilkRequirement() {
    var selectedDrink = document.querySelector('input[name="drink"]:checked');
    var isAmericano = !!selectedDrink && selectedDrink.value === 'Americano';
    var milkGroup = document.querySelector('.option-group[data-category="milk"]');
    if (!milkGroup) return;

    milkGroup.querySelectorAll('input[name="milk"]').forEach(function (input) {
      var row = input.closest('.option-row');
      var isPermanentlyRemoved = row && row.classList.contains('removed-option');

      // ---------------------------------------------------------------------
      // Barista: remove/restore base items, delete custom items.
      // ---------------------------------------------------------------------
      var deleteItemModal = document.getElementById('deleteItemModal');
      var confirmDeleteItemBtn = document.getElementById('confirmDeleteItemBtn');
      var cancelDeleteItemBtn = document.getElementById('cancelDeleteItemBtn');
      var pendingDeleteCategory = null;
      var pendingDeleteValue = null;
      var pendingDeleteRow = null;

      if (isAmericano) {
        input.checked = false;
        if (!isPermanentlyRemoved) input.disabled = true;
        if (row) row.classList.add('option-disabled');
      } else if (!isPermanentlyRemoved) {
        input.disabled = false;
        if (row) row.classList.remove('option-disabled');
      }
    });
  }

  // ---------- Selected option turns the whole row white, not just a dot ----------
  function syncSelectedOptionStyling() {
    document.querySelectorAll('.option-row').forEach(function (row) {
      var input = row.querySelector('input');
      row.classList.toggle('selected-option', !!(input && input.checked));
    });
  }

  document.body.addEventListener('change', function (e) {
    if (!e.target.matches('.option-row input')) return;

    syncSelectedOptionStyling();

    if (e.target.name === 'temp') updateColdOnlyAvailability();
    if (e.target.name === 'drink') updateMilkRequirement();
  });

  updateColdOnlyAvailability();
  updateMilkRequirement();
  syncSelectedOptionStyling();

  // ---------- Word count for notes ----------
  var notes = document.getElementById('notes');
  var wordCount = document.getElementById('wordCount');

  if (notes) {
    notes.addEventListener('input', function () {
      var words = notes.value.trim().length ? notes.value.trim().split(/\s+/) : [];
      if (words.length > 50) {
        words = words.slice(0, 50);
        notes.value = words.join(' ');
      }
      wordCount.textContent = words.length;
    });
  }

  // ---------- Form submission ----------
  var form = document.getElementById('orderForm');
  var formError = document.getElementById('formError');
  var successMessage = document.getElementById('successMessage');

  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      formError.textContent = '';

      if (!form.checkValidity()) {
        form.reportValidity();
        return;
      }

      var formData = new FormData(form);

      fetch('/submit_order', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
        body: formData
      })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (!data.success) return;

          if (data.removed) {
            row.classList.add('removed-option');
            btn.textContent = 'Restore Item';
            btn.classList.add('restore-btn');
            if (input) input.disabled = true;
          } else {
            row.classList.remove('removed-option');
            btn.textContent = 'Temporarily Remove Item';
            btn.classList.remove('restore-btn');
            if (input) {
              if (input.dataset.coldOnly === 'true') {
                updateColdOnlyAvailability();
              } else if (category === 'milk') {
                updateMilkRequirement();
              } else {
                input.disabled = false;
              }
            }
          }
        });
    });
  }

  // ---------------------------------------------------------------------
  // Barista: remove/restore base items, delete custom items.
  // ---------------------------------------------------------------------
  var deleteItemModal = document.getElementById('deleteItemModal');
  var confirmDeleteItemBtn = document.getElementById('confirmDeleteItemBtn');
  var cancelDeleteItemBtn = document.getElementById('cancelDeleteItemBtn');
  var pendingDeleteCategory = null;
  var pendingDeleteValue = null;
  var pendingDeleteRow = null;

  function resetPendingDelete() {
    pendingDeleteCategory = null;
    pendingDeleteValue = null;
    pendingDeleteRow = null;
    if (deleteItemModal) deleteItemModal.style.display = 'none';
  }

  document.body.addEventListener('click', function (e) {
    var btn = e.target.closest('.remove-item-btn');
    if (!btn) return;

    var category = btn.dataset.category;
    var value = btn.dataset.value;
    var isCustom = btn.dataset.custom === 'true';
    var row = btn.closest('.option-row');

    if (isCustom) {
      pendingDeleteCategory = category;
      pendingDeleteValue = value;
      pendingDeleteRow = row;
      if (deleteItemModal) deleteItemModal.style.display = 'flex';
      return;
    }

    var input = row ? row.querySelector('input') : null;
    var formData = new FormData();
    formData.append('category', category);
    formData.append('value', value);

    fetch('/toggle_item', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken },
      body: formData
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (!data.success) return;

        if (data.removed) {
          row.classList.add('removed-option');
          btn.textContent = 'Restore Item';
          btn.classList.add('restore-btn');
          if (input) input.disabled = true;
        } else {
          row.classList.remove('removed-option');
          btn.textContent = 'Temporarily Remove Item';
          btn.classList.remove('restore-btn');
          if (input) {
            if (input.dataset.coldOnly === 'true') {
              updateColdOnlyAvailability();
            } else if (category === 'milk') {
              updateMilkRequirement();
            } else {
              input.disabled = false;
            }
          }
        }
      });
  });

  if (cancelDeleteItemBtn) {
    cancelDeleteItemBtn.addEventListener('click', resetPendingDelete);
  }

  if (deleteItemModal) {
    deleteItemModal.addEventListener('click', function (e) {
      if (e.target === deleteItemModal) resetPendingDelete();
    });
  }

  if (confirmDeleteItemBtn) {
    confirmDeleteItemBtn.addEventListener('click', function () {
      if (!pendingDeleteCategory || !pendingDeleteValue) return;

      var formData = new FormData();
      formData.append('category', pendingDeleteCategory);
      formData.append('value', pendingDeleteValue);
      var rowToRemove = pendingDeleteRow;

      fetch('/delete_custom_item', {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
        body: formData
      })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (data.success && rowToRemove) {
            rowToRemove.remove();
          }
          resetPendingDelete();
        });
    });
  }

  // ---------------------------------------------------------------------
  // Barista: "Stop Taking Orders" toggle.
  // ---------------------------------------------------------------------
  var stopOrdersToggle = document.getElementById('stopOrdersToggle');
  var stopOrdersModal = document.getElementById('stopOrdersModal');
  var confirmStopOrdersBtn = document.getElementById('confirmStopOrdersBtn');
  var cancelStopOrdersBtn = document.getElementById('cancelStopOrdersBtn');

  function commitStoreStatusToggle() {
    fetch('/toggle_store_status', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken }
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (data.success && stopOrdersToggle) {
          stopOrdersToggle.checked = data.orders_closed;
        }
      });
  }

  if (stopOrdersToggle) {
    stopOrdersToggle.addEventListener('change', function () {
      if (stopOrdersToggle.checked) {
        if (stopOrdersModal) stopOrdersModal.style.display = 'flex';
      } else {
        commitStoreStatusToggle();
      }
    });
  }

  if (cancelStopOrdersBtn) {
    cancelStopOrdersBtn.addEventListener('click', function () {
      if (stopOrdersModal) stopOrdersModal.style.display = 'none';
      if (stopOrdersToggle) stopOrdersToggle.checked = false;
    });
  }

  if (stopOrdersModal) {
    stopOrdersModal.addEventListener('click', function (e) {
      if (e.target === stopOrdersModal) {
        stopOrdersModal.style.display = 'none';
        if (stopOrdersToggle) stopOrdersToggle.checked = false;
      }
    });
  }

  if (confirmStopOrdersBtn) {
    confirmStopOrdersBtn.addEventListener('click', function () {
      if (stopOrdersModal) stopOrdersModal.style.display = 'none';
      commitStoreStatusToggle();
    });
  }

});
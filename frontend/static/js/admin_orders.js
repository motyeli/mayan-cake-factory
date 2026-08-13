/**
 * Admin order list.
 *
 * Filters live in the URL query string, so a filtered view can be bookmarked,
 * shared with the person covering the shift, and survives a reload.
 */
(function () {
  'use strict';

  if (!admin.token()) return;

  var PAGE_SIZE = 25;

  var els = {
    form: document.querySelector('[data-filters]'),
    rows: document.querySelector('[data-rows]'),
    empty: document.querySelector('[data-empty]'),
    chips: document.querySelector('[data-active-filters]'),
    showing: document.querySelector('[data-showing]'),
    prev: document.querySelector('[data-prev]'),
    next: document.querySelector('[data-next]'),
    error: document.querySelector('[data-error]')
  };

  var CHIP_LABELS = {
    status: 'Status',
    fulfillment_method: 'Method',
    complexity_level: 'Complexity',
    search: 'Search',
    rush_only: 'Rush only',
    allergen_only: 'Allergen only',
    special_only: 'Special orders'
  };

  var offset = 0;
  var total = 0;

  function currentFilters() {
    var params = new URLSearchParams(window.location.search);
    var filters = {};
    params.forEach(function (value, key) {
      if (value) filters[key] = value;
    });
    return filters;
  }

  function applyFiltersToForm(filters) {
    Object.keys(filters).forEach(function (key) {
      var field = els.form.elements[key];
      if (!field) return;
      if (field.type === 'checkbox') field.checked = filters[key] === 'true';
      else field.value = filters[key];
    });
  }

  function renderChips(filters) {
    els.chips.textContent = '';
    Object.keys(filters).forEach(function (key) {
      if (!CHIP_LABELS[key]) return;
      var li = document.createElement('li');
      li.className = 'chip chip--active';

      var text = filters[key] === 'true'
        ? CHIP_LABELS[key]
        : CHIP_LABELS[key] + ': ' + filters[key];
      li.appendChild(document.createTextNode(text));

      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'chip__remove';
      remove.setAttribute('aria-label', 'Remove filter ' + text);
      remove.textContent = '×';
      remove.addEventListener('click', function () {
        var params = new URLSearchParams(window.location.search);
        params.delete(key);
        window.location.search = params.toString();
      });

      li.appendChild(remove);
      els.chips.appendChild(li);
    });
  }

  function badge(status, label) {
    var span = document.createElement('span');
    span.className = 'status-badge status-badge--' + status.replace(/_/g, '-');
    span.textContent = label || status;
    return span;
  }

  function cell(row, content, className) {
    var td = document.createElement('td');
    if (className) td.className = className;
    if (content instanceof Node) td.appendChild(content);
    else td.textContent = content === null || content === undefined ? '—' : content;
    row.appendChild(td);
    return td;
  }

  function render(data) {
    els.rows.textContent = '';
    total = data.total || 0;

    if (!data.orders.length) {
      els.empty.hidden = false;
    } else {
      els.empty.hidden = true;
    }

    data.orders.forEach(function (order) {
      var tr = document.createElement('tr');

      var link = document.createElement('a');
      link.href = '/admin/orders/' + order.id;
      link.textContent = order.order_number;
      cell(tr, link);

      cell(tr, (order.customer || {}).full_name);
      cell(tr, order.fulfillment_date);
      cell(tr, order.fulfillment_method === 'delivery' ? 'Delivery' : 'Collection');
      cell(tr, badge(order.status, order.status_label));
      cell(tr, order.complexity_level);
      cell(tr, order.production_points);

      var price = document.createElement('span');
      price.textContent = admin.money(order.total_price_cents, order.currency);
      if (order.price_is_estimate) {
        var note = document.createElement('small');
        note.className = 'estimate-flag';
        note.textContent = ' est.';
        price.appendChild(note);
      }
      cell(tr, price, 'numeric');

      var warnings = document.createElement('span');
      warnings.className = 'warning-marks';
      if (order.is_rush_order) {
        var rush = document.createElement('span');
        rush.className = 'mark mark--rush';
        rush.title = 'Rush order';
        rush.textContent = 'Rush';
        warnings.appendChild(rush);
      }
      if (order.has_allergen_warning) {
        var allergen = document.createElement('span');
        allergen.className = 'mark mark--allergen';
        allergen.title = 'Allergen declaration';
        allergen.textContent = 'Allergen';
        warnings.appendChild(allergen);
      }
      cell(tr, warnings);

      els.rows.appendChild(tr);
    });

    var from = total ? offset + 1 : 0;
    var to = Math.min(offset + PAGE_SIZE, total);
    els.showing.textContent = 'Showing ' + from + '–' + to + ' of ' + total;
    els.prev.disabled = offset === 0;
    els.next.disabled = to >= total;
  }

  function load() {
    var filters = currentFilters();
    var params = new URLSearchParams(filters);
    params.set('limit', PAGE_SIZE);
    params.set('offset', offset);

    els.error.hidden = true;
    admin.get('/api/v1/admin/orders?' + params.toString())
      .then(render)
      .catch(function (error) {
        els.error.textContent = error.message;
        els.error.hidden = false;
      });
  }

  els.form.addEventListener('submit', function (event) {
    event.preventDefault();
    var params = new URLSearchParams();
    Array.prototype.forEach.call(els.form.elements, function (field) {
      if (!field.name) return;
      if (field.type === 'checkbox') {
        if (field.checked) params.set(field.name, 'true');
      } else if (field.value) {
        params.set(field.name, field.value);
      }
    });
    window.location.search = params.toString();
  });

  function clearFilters() { window.location.search = ''; }
  document.querySelector('[data-clear]').addEventListener('click', clearFilters);
  document.querySelector('[data-clear-2]').addEventListener('click', clearFilters);

  els.prev.addEventListener('click', function () {
    offset = Math.max(0, offset - PAGE_SIZE);
    load();
  });
  els.next.addEventListener('click', function () {
    offset += PAGE_SIZE;
    load();
  });

  var filters = currentFilters();
  applyFiltersToForm(filters);
  renderChips(filters);
  load();
})();

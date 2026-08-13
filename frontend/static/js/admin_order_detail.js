/**
 * Admin order detail.
 *
 * The status dropdown is populated from `allowed_transitions`, which the
 * backend computes from the state machine and the fulfilment method. So the
 * UI cannot even offer an illegal move — and if it somehow did, the API
 * refuses it with a 409 that is shown verbatim.
 */
(function () {
  'use strict';

  if (!admin.token()) return;

  var orderId = window.location.pathname.split('/').filter(Boolean).pop();

  var els = {
    detail: document.querySelector('[data-detail]'),
    error: document.querySelector('[data-error]'),
    success: document.querySelector('[data-success]'),
    orderNumber: document.querySelector('[data-order-number]'),
    statusBadge: document.querySelector('[data-status-badge]'),
    created: document.querySelector('[data-created]'),
    actions: document.querySelector('[data-actions]'),
    image: document.querySelector('[data-image]'),
    spec: document.querySelector('[data-spec]'),
    customer: document.querySelector('[data-customer]'),
    breakdown: document.querySelector('[data-breakdown]'),
    total: document.querySelector('[data-total]'),
    estimateFlag: document.querySelector('[data-estimate-flag]'),
    production: document.querySelector('[data-production]'),
    reasons: document.querySelector('[data-reasons]'),
    statusSelect: document.querySelector('[data-status-select]'),
    notes: document.querySelector('[data-notes]'),
    history: document.querySelector('[data-history]'),
    audit: document.querySelector('[data-audit]')
  };

  function row(term, value) {
    var wrap = document.createElement('div');
    var dt = document.createElement('dt');
    dt.textContent = term;
    var dd = document.createElement('dd');
    dd.textContent = value === null || value === undefined || value === '' ? '—' : value;
    wrap.appendChild(dt);
    wrap.appendChild(dd);
    return wrap;
  }

  function say(element, message) {
    element.textContent = message;
    element.hidden = false;
    if (element === els.success) {
      setTimeout(function () { element.hidden = true; }, 4000);
    }
  }

  function fail(error) { say(els.error, error.message); }

  function render(data) {
    var order = data.order;
    els.error.hidden = true;

    els.orderNumber.textContent = order.order_number;
    els.statusBadge.className = 'status-badge status-badge--' +
      order.status.replace(/_/g, '-');
    els.statusBadge.textContent = order.status.replace(/_/g, ' ');
    els.created.textContent = 'Created ' + (order.created_at || '').slice(0, 10);

    // Approve and reject only make sense while the order is waiting.
    els.actions.textContent = '';
    if (order.status === 'awaiting_bakery_approval') {
      var approve = document.createElement('button');
      approve.className = 'button button--primary';
      approve.textContent = 'Approve order';
      approve.addEventListener('click', function () {
        admin.post('/api/v1/admin/orders/' + orderId + '/approve', {})
          .then(function () { say(els.success, 'Order approved.'); return load(); })
          .catch(fail);
      });

      var reject = document.createElement('button');
      reject.className = 'button button--secondary';
      reject.textContent = 'Reject order';
      reject.addEventListener('click', function () {
        // A rejection reason is required — the customer will be told.
        var reason = window.prompt('Why is this order being rejected? The customer will be told.');
        if (!reason) return;
        admin.post('/api/v1/admin/orders/' + orderId + '/reject', { reason: reason })
          .then(function () { say(els.success, 'Order rejected.'); return load(); })
          .catch(fail);
      });

      els.actions.appendChild(approve);
      els.actions.appendChild(reject);
    }

    var design = (data.designs || []).filter(function (d) { return d.customer_approved; })[0];
    if (design && design.image_url) {
      els.image.src = design.image_url;
      els.image.hidden = false;
    }

    var spec = design ? (design.structured_specification || {}) : {};
    els.spec.textContent = '';
    els.spec.appendChild(row('Approved version', design ? 'Version ' + design.version_number : '—'));
    els.spec.appendChild(row('Servings', spec.servings));
    els.spec.appendChild(row('Tiers', spec.number_of_tiers));
    els.spec.appendChild(row('Shape', spec.shape));
    els.spec.appendChild(row('Inscription', spec.inscription));
    els.spec.appendChild(row('Colours', (spec.colors || []).join(', ')));
    els.spec.appendChild(row('Allergen notes', (spec.allergen_notes || []).join(', ')));

    var customer = data.customer || {};
    els.customer.textContent = '';
    els.customer.appendChild(row('Name', customer.full_name));
    els.customer.appendChild(row('Email', customer.email));
    els.customer.appendChild(row('Phone', customer.phone));
    els.customer.appendChild(row('Method',
      order.fulfillment_method === 'delivery' ? 'Delivery' : 'Collection'));
    els.customer.appendChild(row('Date', order.fulfillment_date));
    if (order.delivery_address) {
      els.customer.appendChild(row('Address', order.delivery_address));
      els.customer.appendChild(row('Distance',
        order.delivery_distance_km ? order.delivery_distance_km + ' km' : '—'));
    }
    els.customer.appendChild(row('Customer notes', order.customer_notes));

    var price = order.price_breakdown || {};
    els.breakdown.textContent = '';
    (price.lines || []).forEach(function (line) {
      els.breakdown.appendChild(row(line.label, admin.money(line.amount_cents, order.currency)));
    });
    els.total.textContent = admin.money(order.total_price_cents, order.currency);
    els.estimateFlag.hidden = !order.price_is_estimate;

    els.production.textContent = '';
    els.production.appendChild(row('Complexity level', order.complexity_level));
    els.production.appendChild(row('Production points', order.production_points));
    els.production.appendChild(row('Rush order', order.is_rush_order ? 'Yes' : 'No'));
    els.production.appendChild(row('Payment status', order.payment_status));
    els.production.appendChild(row('Amount paid',
      admin.money(order.amount_paid_cents, order.currency)));

    els.reasons.textContent = '';
    (order.manual_approval_reasons || []).forEach(function (reason) {
      var li = document.createElement('li');
      li.textContent = reason;
      els.reasons.appendChild(li);
    });

    els.statusSelect.textContent = '';
    (data.allowed_transitions || []).forEach(function (option) {
      var opt = document.createElement('option');
      opt.value = option.status;
      opt.textContent = option.label;
      els.statusSelect.appendChild(opt);
    });
    if (!(data.allowed_transitions || []).length) {
      var none = document.createElement('option');
      none.textContent = 'No further changes possible';
      els.statusSelect.appendChild(none);
      els.statusSelect.disabled = true;
      document.querySelector('[data-change-status]').disabled = true;
    }

    els.notes.textContent = order.internal_notes || 'No notes yet.';

    function timeline(target, entries, format) {
      target.textContent = '';
      entries.forEach(function (entry) {
        var li = document.createElement('li');
        li.textContent = format(entry);
        target.appendChild(li);
      });
    }

    timeline(els.history, data.status_history || [], function (h) {
      return (h.created_at || '').slice(0, 16).replace('T', ' ') + ' — ' +
             (h.previous_status ? h.previous_status + ' → ' : '') + h.new_status +
             ' (' + (h.changed_by_label || 'system') + ')' +
             (h.reason ? ' · ' + h.reason : '');
    });

    timeline(els.audit, data.audit_log || [], function (a) {
      return (a.created_at || '').slice(0, 16).replace('T', ' ') + ' — ' + a.action +
             ' by ' + (a.actor_label || 'system') + (a.reason ? ' · ' + a.reason : '');
    });

    els.detail.hidden = false;
  }

  function load() {
    return admin.get('/api/v1/admin/orders/' + orderId).then(render).catch(fail);
  }

  document.querySelector('[data-change-status]').addEventListener('click', function () {
    admin.post('/api/v1/admin/orders/' + orderId + '/status', {
      status: els.statusSelect.value,
      reason: document.getElementById('status-reason').value || null
    })
      .then(function () { say(els.success, 'Status updated.'); return load(); })
      .catch(fail);
  });

  document.querySelector('[data-override]').addEventListener('click', function () {
    var amount = parseFloat(document.getElementById('new-total').value);
    var reason = document.getElementById('override-reason').value.trim();
    if (isNaN(amount)) { say(els.error, 'Enter the new total.'); return; }
    if (!reason) { say(els.error, 'A reason is required for a price change.'); return; }

    admin.patch('/api/v1/admin/orders/' + orderId + '/price', {
      total_cents: Math.round(amount * 100),
      reason: reason
    })
      .then(function () { say(els.success, 'Price updated and recorded.'); return load(); })
      .catch(fail);
  });

  document.querySelector('[data-add-note]').addEventListener('click', function () {
    var note = document.getElementById('note').value.trim();
    if (!note) return;
    admin.post('/api/v1/admin/orders/' + orderId + '/notes', { note: note })
      .then(function () {
        document.getElementById('note').value = '';
        say(els.success, 'Note added.');
        return load();
      })
      .catch(fail);
  });

  load();
})();

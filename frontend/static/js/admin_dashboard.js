/**
 * Dashboard.
 *
 * Every figure is rendered exactly as the backend reports it. In particular
 * the four money numbers are never added together — see spec section 32.
 */
(function () {
  'use strict';

  if (!admin.token()) return;

  function set(selector, value) {
    var el = document.querySelector(selector);
    if (el) el.textContent = value;
  }

  function list(selector, items, render, emptySelector) {
    var el = document.querySelector(selector);
    el.textContent = '';
    if (!items.length) {
      var empty = document.querySelector(emptySelector);
      if (empty) empty.hidden = false;
      return;
    }
    items.forEach(function (item) { el.appendChild(render(item)); });
  }

  admin.get('/api/v1/admin/dashboard')
    .then(function (data) {
      set('[data-orders-today]', data.orders_today);
      set('[data-orders-week]', data.orders_this_week);
      set('[data-points-used]', data.points_used_today);
      set('[data-points-limit]', 'of ' + data.points_limit_today);
      set('[data-awaiting]', data.awaiting_approval);

      var bar = document.querySelector('[data-points-bar]');
      var ratio = data.points_limit_today
        ? Math.min(100, (data.points_used_today / data.points_limit_today) * 100)
        : 0;
      bar.style.width = ratio + '%';
      if (ratio >= 100) bar.classList.add('is-full');

      var m = data.money || {};
      set('[data-money-confirmed]', admin.money(m.confirmed_order_value_cents));
      set('[data-money-paid]', admin.money(m.amount_paid_cents));
      set('[data-money-outstanding]', admin.money(m.outstanding_cents));
      set('[data-money-estimated]', admin.money(m.estimated_special_order_value_cents));

      list('[data-load]', data.production_load || [], function (day) {
        var li = document.createElement('li');

        var label = document.createElement('span');
        label.className = 'load-list__date';
        label.textContent = day.date;

        var meter = document.createElement('div');
        meter.className = 'meter';
        var fill = document.createElement('div');
        fill.className = 'meter__fill' + (day.full ? ' is-full' : '');
        fill.style.width = Math.min(100, (day.used / (day.max || 1)) * 100) + '%';
        meter.appendChild(fill);

        var count = document.createElement('span');
        count.className = 'load-list__count';
        count.textContent = day.used + '/' + day.max + (day.full ? ' · full' : '');

        li.appendChild(label);
        li.appendChild(meter);
        li.appendChild(count);
        return li;
      });

      list('[data-approvals]', data.awaiting_orders || [], function (order) {
        var li = document.createElement('li');

        var link = document.createElement('a');
        link.href = '/admin/orders?search=' + encodeURIComponent(order.order_number);
        link.textContent = order.order_number;

        var when = document.createElement('span');
        when.className = 'helper-text';
        when.textContent = order.fulfillment_date + ' · ' + admin.money(order.total_price_cents);

        li.appendChild(link);
        li.appendChild(when);

        (order.reasons || []).forEach(function (reason) {
          var badge = document.createElement('span');
          badge.className = 'badge';
          badge.textContent = reason;
          li.appendChild(badge);
        });
        return li;
      }, '[data-approvals-empty]');

      var plain = function (text) {
        var li = document.createElement('li');
        li.textContent = text;
        return li;
      };
      list('[data-allergens]', data.allergen_warnings || [], plain, '[data-allergens-empty]');
      list('[data-rush]', data.rush_orders || [], plain, '[data-rush-empty]');
    })
    .catch(function (error) {
      var el = document.querySelector('[data-error]');
      el.textContent = error.message;
      el.hidden = false;
    });
})();

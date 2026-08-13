/**
 * Specification confirmation.
 *
 * The confirm button is driven entirely by the backend's `can_confirm`. This
 * page never decides whether a cake is buildable — it shows what the
 * feasibility engine decided and why.
 */
(function () {
  'use strict';

  var TOKEN_KEY = 'mayan.session.token';
  var token = sessionStorage.getItem(TOKEN_KEY);

  var els = {
    spec: document.querySelector('[data-spec]'),
    breakdown: document.querySelector('[data-breakdown]'),
    total: document.querySelector('[data-total]'),
    priceNote: document.querySelector('[data-price-note]'),
    allergen: document.querySelector('[data-allergen]'),
    blockers: document.querySelector('[data-blockers]'),
    blockerText: document.querySelector('[data-blocker-text]'),
    confirm: document.querySelector('[data-confirm]'),
    error: document.querySelector('[data-error]')
  };

  var LABELS = [
    ['event_type', 'Event type'], ['event_date', 'Date'], ['servings', 'Servings'],
    ['size', 'Size'], ['shape', 'Shape'], ['tiers', 'Tiers'],
    ['cake_flavor', 'Flavour'], ['filling', 'Filling'], ['frosting', 'Frosting'],
    ['design_style', 'Style'], ['colors', 'Colours'], ['decorations', 'Decorations'],
    ['inscription', 'Inscription'], ['dietary_requirements', 'Dietary requirements'],
    ['fulfillment_method', 'Fulfilment'], ['delivery_address', 'Delivery address']
  ];

  function money(cents, currency) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: currency || 'USD', minimumFractionDigits: 2
    }).format((cents || 0) / 100);
  }

  function row(term, value, muted) {
    var wrap = document.createElement('div');
    var dt = document.createElement('dt');
    dt.textContent = term;
    var dd = document.createElement('dd');
    dd.textContent = value;
    if (muted) dd.className = 'is-unset';
    wrap.appendChild(dt);
    wrap.appendChild(dd);
    return wrap;
  }

  function showError(message) {
    els.error.textContent = message;
    els.error.hidden = false;
  }

  function render(data) {
    var display = data.specification_display || {};

    els.spec.textContent = '';
    LABELS.forEach(function (pair) {
      var value = display[pair[0]];
      var empty = value === null || value === undefined || value === '' ||
                  (Array.isArray(value) && value.length === 0);
      // Delivery address only matters for delivery orders.
      if (pair[0] === 'delivery_address' && display.fulfillment_method !== 'delivery') return;
      els.spec.appendChild(row(
        pair[1],
        empty ? 'Not chosen yet' : (Array.isArray(value) ? value.join(', ') : String(value)),
        empty
      ));
    });

    var price = data.price || {};
    els.breakdown.textContent = '';
    (price.lines || []).forEach(function (line) {
      els.breakdown.appendChild(row(line.label, money(line.amount_cents, price.currency)));
    });
    els.total.textContent = money(price.total_cents, price.currency);

    if (price.is_estimate) {
      els.priceNote.hidden = false;
      els.priceNote.textContent = 'Estimated price, subject to bakery approval';
    }

    if (data.disclaimers && data.disclaimers.allergen) {
      els.allergen.textContent = data.disclaimers.allergen;
    }

    // The backend decides. This page only reports the decision.
    var problems = (data.consistency_problems || []).concat(data.missing_information || []);
    if (!data.can_confirm) {
      els.confirm.setAttribute('aria-disabled', 'true');
      els.blockers.hidden = false;
      els.blockerText.textContent = problems.length
        ? problems.join(' ')
        : 'This design needs a change before we can create it.';
    } else {
      els.confirm.removeAttribute('aria-disabled');
      els.blockers.hidden = true;
    }
  }

  function load() {
    if (!token) {
      window.location.href = '/design';
      return;
    }
    // POST /validate returns the same view plus the confirm decision and the
    // disclaimers, and marks the specification confirmed when it is allowed.
    api.post('/api/v1/design-sessions/' + token + '/validate', {})
      .then(render)
      .catch(function (error) { showError(error.message); });
  }

  els.confirm.addEventListener('click', function () {
    if (els.confirm.getAttribute('aria-disabled') === 'true') return;
    els.confirm.disabled = true;
    els.confirm.textContent = 'Creating your design…';

    api.post('/api/v1/design-sessions/' + token + '/generate-design', {})
      .then(function () { window.location.href = '/design/preview'; })
      .catch(function (error) {
        els.confirm.disabled = false;
        els.confirm.textContent = 'Create my design';
        showError(error.message);
      });
  });

  load();
})();

/**
 * Home page content.
 *
 * Prices, delivery fees, lead time, allergen wording, payment arrangement and
 * the cancellation policy all come from the catalog endpoint. Nothing about
 * the business is written into the template, so the marketing page and the
 * rule engine cannot disagree — which is exactly what the generated design
 * copy did, promising a two-week lead time and a credit-card deposit.
 */
(function () {
  'use strict';

  function money(cents, currency) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: currency || 'USD', maximumFractionDigits: 0
    }).format((cents || 0) / 100);
  }

  function setText(selector, value) {
    var el = document.querySelector(selector);
    if (el && value) el.textContent = value;
  }

  function renderStyles(styles) {
    var list = document.querySelector('[data-styles]');
    var status = document.querySelector('[data-styles-status]');
    styles.forEach(function (style) {
      var item = document.createElement('li');
      item.className = 'style-card';

      var name = document.createElement('h3');
      name.textContent = style.name;

      var about = document.createElement('p');
      about.textContent = style.description || '';

      item.appendChild(name);
      item.appendChild(about);
      list.appendChild(item);
    });
    status.hidden = true;
    list.hidden = false;
  }

  function renderSizes(sizes, currency) {
    var list = document.querySelector('[data-sizes]');
    // Three representative sizes across the range, chosen from real rows
    // rather than hard-coded, so editing the catalog updates the page.
    var picks = [sizes[0], sizes[Math.floor(sizes.length / 2)], sizes[sizes.length - 2]]
      .filter(Boolean);

    picks.forEach(function (size) {
      var item = document.createElement('li');
      item.className = 'price-card';

      var name = document.createElement('h3');
      name.textContent = size.name;

      var amount = document.createElement('p');
      amount.className = 'price-card__amount';
      amount.textContent = 'from ' + money(size.base_price_cents, currency);

      var serves = document.createElement('p');
      serves.className = 'helper-text';
      serves.textContent = size.min_servings + '–' + size.max_servings + ' servings';

      item.appendChild(name);
      item.appendChild(amount);
      item.appendChild(serves);
      list.appendChild(item);
    });
  }

  function renderZones(zones, currency) {
    var list = document.querySelector('[data-zones]');
    zones.forEach(function (zone) {
      // Zones needing approval have no published fee — showing "$0" would
      // read as free delivery.
      if (zone.requires_manual_approval) return;
      var item = document.createElement('li');
      item.textContent = zone.name + ' — ' + money(zone.delivery_fee_cents, currency);
      list.appendChild(item);
    });
  }

  function renderSlots(slots) {
    if (!slots.length) return;
    var first = slots[0].start_time.slice(0, 5);
    var last = slots[slots.length - 1].end_time.slice(0, 5);
    setText('[data-slot-range]', first + '–' + last);
  }

  api.get('/api/v1/catalog')
    .then(function (catalog) {
      var settings = catalog.settings || {};
      var currency = settings.currency || 'USD';

      renderStyles(catalog.styles || []);
      renderSizes(catalog.sizes || [], currency);
      renderZones(catalog.delivery_zones || [], currency);
      renderSlots(catalog.time_slots || []);

      var lead = settings.default_lead_time_hours;
      if (lead) {
        setText('[data-lead-time]',
          'We ask for at least ' + lead + ' hours’ notice. Shorter notice is a rush ' +
          'order, which the bakery reviews before confirming.');
      }

      var revisions = settings.max_revisions;
      if (revisions) setText('[data-max-revisions]', revisions);

      setText('[data-allergen]', settings.allergen_disclaimer);
      setText('[data-payment]', settings.payment_instructions);
      setText('[data-cancellation]', settings.cancellation_policy);
      setText('[data-inspiration]', settings.inspiration_disclaimer);
      setText('[data-visual-disclaimer]', settings.visual_disclaimer);
      if (settings.bakery_address) {
        setText('[data-address]', settings.bakery_address);
      }
    })
    .catch(function (error) {
      var status = document.querySelector('[data-styles-status]');
      if (status) {
        status.textContent = 'We could not load our catalog just now. ' + error.message;
      }
    });
})();

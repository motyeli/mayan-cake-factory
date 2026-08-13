/**
 * Order confirmation.
 *
 * Reads the order by its number. Status wording, the payment arrangement and
 * the cancellation policy all come from the backend — a page that hard-coded
 * "confirmed" would keep saying so after the bakery rejected the order.
 */
(function () {
  'use strict';

  var els = {
    order: document.querySelector('[data-order]'),
    status: document.querySelector('[data-status]'),
    heading: document.querySelector('[data-heading]'),
    orderNumber: document.querySelector('[data-order-number]'),
    approvalNote: document.querySelector('[data-approval-note]'),
    image: document.querySelector('[data-image]'),
    spec: document.querySelector('[data-spec]'),
    fulfilment: document.querySelector('[data-fulfilment]'),
    breakdown: document.querySelector('[data-breakdown]'),
    total: document.querySelector('[data-total]'),
    priceNote: document.querySelector('[data-price-note]'),
    payment: document.querySelector('[data-payment]'),
    visualDisclaimer: document.querySelector('[data-visual-disclaimer]'),
    cancellation: document.querySelector('[data-cancellation]'),
    link: document.querySelector('[data-link]'),
    linkNote: document.querySelector('[data-link-note]'),
    copy: document.querySelector('[data-copy]'),
    error: document.querySelector('[data-error]')
  };

  var STATUS_WORDING = {
    confirmed: ['Confirmed', 'Your order is confirmed'],
    awaiting_bakery_approval: ['Awaiting bakery approval', 'Your order has been received'],
    in_production: ['In production', 'Your cake is being made'],
    ready_for_pickup: ['Ready for collection', 'Your cake is ready'],
    out_for_delivery: ['Out for delivery', 'Your cake is on its way'],
    completed: ['Completed', 'Thank you'],
    cancelled: ['Cancelled', 'This order was cancelled']
  };

  function money(cents, currency) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: currency || 'USD', minimumFractionDigits: 2
    }).format((cents || 0) / 100);
  }

  function row(term, value) {
    var wrap = document.createElement('div');
    var dt = document.createElement('dt');
    dt.textContent = term;
    var dd = document.createElement('dd');
    dd.textContent = value;
    wrap.appendChild(dt);
    wrap.appendChild(dd);
    return wrap;
  }

  function orderNumberFromUrl() {
    var parts = window.location.pathname.split('/').filter(Boolean);
    return parts[parts.length - 1];
  }

  function render(order) {
    var wording = STATUS_WORDING[order.status] || ['Received', 'Your order has been received'];
    els.status.textContent = wording[0];
    els.heading.textContent = wording[1];
    els.orderNumber.textContent = order.order_number;

    if (order.status === 'awaiting_bakery_approval') {
      els.approvalNote.hidden = false;
      els.approvalNote.textContent =
        'Mayan will review this design personally and confirm it with you. ' +
        'The price shown is an estimate until then.';
    }

    if (order.image_url) {
      els.image.src = order.image_url;
      els.image.hidden = false;
    }

    var display = order.specification_display || {};
    els.spec.textContent = '';
    [['Event', 'event_type'], ['Date', 'event_date'], ['Servings', 'servings'],
     ['Size', 'size'], ['Flavour', 'cake_flavor'], ['Filling', 'filling'],
     ['Finish', 'frosting'], ['Style', 'design_style'], ['Colours', 'colors'],
     ['Decorations', 'decorations'], ['Inscription', 'inscription'],
     ['Dietary', 'dietary_requirements']]
      .forEach(function (pair) {
        var value = display[pair[1]];
        if (value === null || value === undefined || value === '' ||
            (Array.isArray(value) && !value.length)) return;
        els.spec.appendChild(row(pair[0], Array.isArray(value) ? value.join(', ') : value));
      });

    els.fulfilment.textContent = '';
    els.fulfilment.appendChild(row('Method',
      order.fulfillment_method === 'delivery' ? 'Delivery' : 'Collection'));
    els.fulfilment.appendChild(row('Date', order.fulfillment_date));
    if (order.time_slot) els.fulfilment.appendChild(row('Time', order.time_slot));
    if (order.delivery_address) {
      els.fulfilment.appendChild(row('Address', order.delivery_address));
    }

    els.breakdown.textContent = '';
    var price = order.price_breakdown || {};
    (price.lines || []).forEach(function (line) {
      els.breakdown.appendChild(row(line.label, money(line.amount_cents, order.currency)));
    });
    els.total.textContent = money(order.total_price_cents, order.currency);

    if (order.price_is_estimate) {
      els.priceNote.hidden = false;
      els.priceNote.textContent = 'Estimated price, subject to bakery approval';
    }

    els.payment.textContent = order.payment_instructions || '';
    els.visualDisclaimer.textContent = order.visual_disclaimer || '';
    els.cancellation.textContent = order.cancellation_policy || '';

    if (order.return_url) {
      els.link.value = order.return_url;
      els.linkNote.textContent = order.return_link_note || '';
    }

    els.order.hidden = false;
  }

  els.copy.addEventListener('click', function () {
    els.link.select();
    navigator.clipboard.writeText(els.link.value).then(function () {
      els.copy.textContent = 'Copied';
      setTimeout(function () { els.copy.textContent = 'Copy'; }, 2000);
    });
  });

  api.get('/api/v1/orders/' + encodeURIComponent(orderNumberFromUrl()))
    .then(render)
    .catch(function (error) {
      els.error.textContent = error.message;
      els.error.hidden = false;
    });
})();

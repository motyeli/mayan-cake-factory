/**
 * The cake design conversation.
 *
 * Every number shown here comes from the backend. This file formats and
 * displays; it never computes a price, decides availability, or judges whether
 * a specification is complete. The session token lives in sessionStorage so a
 * reload resumes the same conversation.
 */
(function () {
  'use strict';

  var TOKEN_KEY = 'mayan.session.token';

  var els = {
    thread: document.querySelector('[data-thread]'),
    composer: document.querySelector('[data-composer]'),
    input: document.getElementById('message'),
    send: document.querySelector('[data-send]'),
    upload: document.querySelector('[data-upload]'),
    suggestions: document.querySelector('[data-suggestions]'),
    spec: document.querySelector('[data-spec]'),
    price: document.querySelector('[data-price]'),
    priceNote: document.querySelector('[data-price-note]'),
    breakdown: document.querySelector('[data-breakdown]'),
    breakdownToggle: document.querySelector('[data-breakdown-toggle]'),
    availability: document.querySelector('[data-availability]'),
    availabilityDot: document.querySelector('[data-availability-dot]'),
    availabilityText: document.querySelector('[data-availability-text]'),
    review: document.querySelector('[data-review]'),
    missing: document.querySelector('[data-missing]'),
    error: document.querySelector('[data-error]')
  };

  // Order and labels for the running summary. Fields stay listed even when
  // unknown, so the customer can see what is still to decide.
  var SPEC_FIELDS = [
    ['event_type', 'Event'],
    ['event_date', 'Date'],
    ['servings', 'Servings'],
    ['size', 'Size'],
    ['shape', 'Shape'],
    ['tiers', 'Tiers'],
    ['cake_flavor', 'Flavour'],
    ['filling', 'Filling'],
    ['frosting', 'Finish'],
    ['design_style', 'Style'],
    ['colors', 'Colours'],
    ['decorations', 'Decorations'],
    ['inscription', 'Inscription'],
    ['dietary_requirements', 'Dietary'],
    ['fulfillment_method', 'Collection or delivery']
  ];

  var COLOUR_SWATCHES = {
    white: '#FFFFFF', ivory: '#FFFFF0', cream: '#FFFDD0', 'light pink': '#FADCE4',
    pink: '#F8C8D8', blush: '#F2C6C2', red: '#C43D3D', burgundy: '#7B2D3B',
    orange: '#E8A15C', peach: '#FFCBA4', yellow: '#F5DE8C', gold: '#C9A227',
    green: '#8FA97C', sage: '#B2C2A6', mint: '#B8E0D2', blue: '#9FC0DE',
    navy: '#2C3E56', purple: '#B29AC4', lilac: '#C9B6DB', lavender: '#D3C4E3',
    black: '#2B2B2B', silver: '#C7CBD1', grey: '#B9B4AE', brown: '#8C6239'
  };

  function money(cents, currency) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency || 'USD',
      minimumFractionDigits: 2
    }).format((cents || 0) / 100);
  }

  function showError(message) {
    els.error.textContent = message;
    els.error.hidden = false;
  }

  function clearError() {
    els.error.hidden = true;
    els.error.textContent = '';
  }

  // --------------------------------------------------------------- render

  function addMessage(role, text) {
    var wrap = document.createElement('div');
    wrap.className = 'message message--' + role;

    var who = document.createElement('div');
    who.className = 'message__role';
    who.textContent = role === 'user' ? 'You' : 'Maison Mayan';

    var bubble = document.createElement('div');
    bubble.className = 'message__bubble';
    bubble.textContent = text;   // textContent, never innerHTML

    wrap.appendChild(who);
    wrap.appendChild(bubble);
    els.thread.appendChild(wrap);
    els.thread.scrollTop = els.thread.scrollHeight;
    return wrap;
  }

  function showTyping() {
    var wrap = document.createElement('div');
    wrap.className = 'message message--assistant';
    wrap.setAttribute('data-typing', '');
    wrap.innerHTML = '<div class="message__bubble"><span class="typing">' +
                     '<span></span><span></span><span></span></span></div>';
    els.thread.appendChild(wrap);
    els.thread.scrollTop = els.thread.scrollHeight;
    return wrap;
  }

  function renderSuggestions(items) {
    els.suggestions.textContent = '';
    (items || []).forEach(function (text) {
      var chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip';
      chip.textContent = text;
      chip.addEventListener('click', function () { send(text); });
      els.suggestions.appendChild(chip);
    });
  }

  function renderSpec(display) {
    els.spec.textContent = '';
    SPEC_FIELDS.forEach(function (pair) {
      var value = display[pair[0]];
      var row = document.createElement('div');

      var dt = document.createElement('dt');
      dt.textContent = pair[1];

      var dd = document.createElement('dd');
      var empty = value === null || value === undefined || value === '' ||
                  (Array.isArray(value) && value.length === 0);

      if (empty) {
        dd.textContent = 'Not chosen yet';
        dd.className = 'is-unset';
      } else if (pair[0] === 'colors') {
        var swatches = document.createElement('span');
        swatches.className = 'swatches';
        value.forEach(function (name) {
          var dot = document.createElement('span');
          dot.className = 'swatch';
          dot.style.background = COLOUR_SWATCHES[name] || '#DDD5C8';
          dot.title = name;
          swatches.appendChild(dot);
        });
        dd.appendChild(swatches);
        dd.appendChild(document.createTextNode(' ' + value.join(', ')));
      } else {
        dd.textContent = Array.isArray(value) ? value.join(', ') : String(value);
      }

      row.appendChild(dt);
      row.appendChild(dd);
      els.spec.appendChild(row);
    });
  }

  function renderPrice(price) {
    if (!price || !price.total_cents) {
      els.price.textContent = '—';
      els.breakdownToggle.hidden = true;
      els.priceNote.hidden = true;
      return;
    }

    els.price.textContent = money(price.total_cents, price.currency);
    els.priceNote.hidden = !price.is_estimate;
    if (price.is_estimate) {
      els.priceNote.textContent = 'Estimated price, subject to bakery approval';
    }

    els.breakdown.textContent = '';
    (price.lines || []).forEach(function (line) {
      var row = document.createElement('div');
      var dt = document.createElement('dt');
      dt.textContent = line.label;
      var dd = document.createElement('dd');
      dd.textContent = money(line.amount_cents, price.currency);
      row.appendChild(dt);
      row.appendChild(dd);
      els.breakdown.appendChild(row);
    });
    els.breakdownToggle.hidden = false;
  }

  function renderStatus(result) {
    var missing = result.missing_information || [];

    if (missing.length) {
      els.missing.textContent = missing.length + ' detail' +
        (missing.length === 1 ? '' : 's') + ' still needed';
      els.review.setAttribute('aria-disabled', 'true');
    } else {
      els.missing.textContent = 'Everything we need is here.';
      els.review.removeAttribute('aria-disabled');
    }

    // Feasibility notes come from the deterministic engine, not the model.
    var feasibility = result.feasibility;
    if (feasibility && feasibility.outcome && feasibility.outcome !== 'allow') {
      els.availability.hidden = false;
      els.availabilityDot.className = 'dot dot--warn';
      els.availabilityText.textContent = feasibility.outcome === 'reject'
        ? 'This design needs changing before we can make it.'
        : 'The bakery will review this order personally.';
    } else if (result.specification_display && result.specification_display.event_date) {
      els.availability.hidden = false;
      els.availabilityDot.className = 'dot dot--ok';
      els.availabilityText.textContent = result.specification_display.event_date + ' looks possible';
    }
  }

  function applyTurn(result) {
    if (result.specification_display) renderSpec(result.specification_display);
    renderPrice(result.price);
    renderStatus(result);
    renderSuggestions(result.suggested_replies);
  }

  // ---------------------------------------------------------------- flow

  function setBusy(busy) {
    els.send.disabled = busy;
    els.input.disabled = busy;
  }

  function send(text) {
    var message = (text || els.input.value || '').trim();
    if (!message) return;

    clearError();
    addMessage('user', message);
    els.input.value = '';
    renderSuggestions([]);
    setBusy(true);
    var typing = showTyping();

    api.post('/api/v1/design-sessions/' + token() + '/messages', { message: message })
      .then(function (result) {
        typing.remove();
        addMessage('assistant', result.reply);
        applyTurn(result);
      })
      .catch(function (error) {
        typing.remove();
        showError(error.message);
      })
      .then(function () {
        setBusy(false);
        els.input.focus();
      });
  }

  function token() {
    return sessionStorage.getItem(TOKEN_KEY);
  }

  function start() {
    var saved = token();
    if (saved) {
      return api.get('/api/v1/design-sessions/' + saved)
        .then(function (session) {
          (session.messages || []).forEach(function (m) {
            addMessage(m.role === 'user' ? 'user' : 'assistant', m.message);
          });
          applyTurn(session);
        })
        .catch(function () {
          // Expired or unknown link: start fresh rather than stranding them.
          sessionStorage.removeItem(TOKEN_KEY);
          return start();
        });
    }

    return api.post('/api/v1/design-sessions', {})
      .then(function (created) {
        sessionStorage.setItem(TOKEN_KEY, created.token);
        addMessage('assistant', created.turn.reply);
        applyTurn(created.turn);
      })
      .catch(function (error) {
        showError('We could not start a design session. ' + error.message);
      });
  }

  // -------------------------------------------------------------- wiring

  els.composer.addEventListener('submit', function (event) {
    event.preventDefault();
    send();
  });

  // Enter sends, Shift+Enter makes a new line.
  els.input.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  });

  els.breakdownToggle.addEventListener('click', function () {
    var hidden = els.breakdown.hidden;
    els.breakdown.hidden = !hidden;
    els.breakdownToggle.textContent = hidden ? 'Hide breakdown' : 'See breakdown';
  });

  els.upload.addEventListener('change', function () {
    var file = els.upload.files && els.upload.files[0];
    if (!file) return;

    var form = new FormData();
    form.append('file', file);
    form.append('asset_type', 'inspiration');

    clearError();
    api.request('/api/v1/design-sessions/' + token() + '/uploads', {
      method: 'POST', body: form
    })
      .then(function (result) {
        addMessage('user', 'Sent an inspiration image: ' + file.name);
        addMessage('assistant', result.disclaimer ||
          'Thank you — an inspiration image is a design direction, not a guarantee of an exact copy.');
      })
      .catch(function (error) { showError(error.message); })
      .then(function () { els.upload.value = ''; });
  });

  els.review.addEventListener('click', function () {
    if (els.review.getAttribute('aria-disabled') === 'true') return;
    window.location.href = '/design/summary';
  });

  start();
})();

/**
 * Design preview, revisions and version history.
 *
 * Generation is asynchronous — about a minute with a real provider — so this
 * polls the version list and shows staged progress. The revision counter here
 * is informational; the backend refuses the fourth revision with a 409
 * regardless of what this page believes.
 */
(function () {
  'use strict';

  var TOKEN_KEY = 'mayan.session.token';
  var token = sessionStorage.getItem(TOKEN_KEY);

  // Reassurance that changes as time passes, so a slow generation reads as
  // work in progress rather than a stuck page.
  var STAGES = [
    'Creating your design. This usually takes about a minute.',
    'Shaping the tiers and finish…',
    'Adding your colours and decorations…',
    'Almost there — finishing the details…'
  ];

  var els = {
    stage: document.querySelector('[data-stage]'),
    progress: document.querySelector('[data-progress]'),
    progressText: document.querySelector('[data-progress-text]'),
    image: document.querySelector('[data-image]'),
    versions: document.querySelector('[data-versions]'),
    spec: document.querySelector('[data-spec]'),
    price: document.querySelector('[data-price]'),
    priceNote: document.querySelector('[data-price-note]'),
    disclaimer: document.querySelector('[data-disclaimer]'),
    revision: document.getElementById('revision'),
    revise: document.querySelector('[data-revise]'),
    revisionCount: document.querySelector('[data-revision-count]'),
    approve: document.querySelector('[data-approve]'),
    error: document.querySelector('[data-error]')
  };

  var selected = null;
  var polling = null;
  var stageIndex = 0;

  function money(cents, currency) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: currency || 'USD', minimumFractionDigits: 2
    }).format((cents || 0) / 100);
  }

  function showError(message) {
    els.error.textContent = message;
    els.error.hidden = false;
  }

  function clearError() { els.error.hidden = true; }

  function showGenerating(on) {
    els.progress.hidden = !on;
    els.image.hidden = on;
    if (!on) {
      stageIndex = 0;
      return;
    }
    els.progressText.textContent = STAGES[stageIndex % STAGES.length];
    stageIndex += 1;
  }

  function select(version) {
    selected = version;

    if (version.image_url) {
      els.image.src = version.image_url;
      els.image.alt = 'Version ' + version.version_number + ' of your cake design';
      showGenerating(false);
    } else if (version.status === 'failed') {
      showGenerating(false);
      showError('That design could not be created. Please request it again.');
    } else {
      showGenerating(true);
    }

    els.price.textContent = money(version.price_cents);

    var spec = version.structured_specification || {};
    els.spec.textContent = '';
    [['Version', 'Version ' + version.version_number],
     ['Requested change', version.revision_request || 'Original design']]
      .forEach(function (pair) {
        var row = document.createElement('div');
        var dt = document.createElement('dt');
        dt.textContent = pair[0];
        var dd = document.createElement('dd');
        dd.textContent = pair[1];
        row.appendChild(dt);
        row.appendChild(dd);
        els.spec.appendChild(row);
      });

    els.approve.disabled = !version.image_url;

    Array.prototype.forEach.call(els.versions.children, function (li) {
      li.classList.toggle('is-selected', li.getAttribute('data-id') === version.id);
    });
  }

  function renderVersions(data) {
    var versions = data.designs || [];
    els.versions.textContent = '';

    versions.forEach(function (version) {
      var li = document.createElement('li');
      li.className = 'version';
      li.setAttribute('data-id', version.id);
      if (version.customer_approved) li.classList.add('is-approved');

      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'version__button';

      if (version.image_url) {
        var img = document.createElement('img');
        img.src = version.image_url;
        img.alt = '';
        img.loading = 'lazy';
        button.appendChild(img);
      } else {
        var placeholder = document.createElement('span');
        placeholder.className = 'version__pending';
        placeholder.textContent = version.status === 'failed' ? 'Failed' : 'Creating…';
        button.appendChild(placeholder);
      }

      var label = document.createElement('span');
      label.className = 'version__label';
      label.textContent = 'Version ' + version.version_number;

      var price = document.createElement('span');
      price.className = 'version__price';
      price.textContent = money(version.price_cents);

      button.appendChild(label);
      button.appendChild(price);
      button.addEventListener('click', function () { select(version); });

      li.appendChild(button);
      els.versions.appendChild(li);
    });

    var remaining = data.revisions_remaining;
    els.revisionCount.textContent = remaining > 0
      ? remaining + ' of ' + data.max_revisions + ' free revisions left'
      : 'You have used all ' + data.max_revisions + ' free revisions. You can still ' +
        'choose any earlier version above.';
    els.revise.disabled = remaining <= 0;

    if (data.disclaimer) els.disclaimer.textContent = data.disclaimer;

    // Keep the customer on the version they were looking at; otherwise show
    // the newest, which is what they just asked for.
    var keep = selected && versions.filter(function (v) { return v.id === selected.id; })[0];
    select(keep || versions[versions.length - 1] || {});

    return versions;
  }

  function poll() {
    return api.get('/api/v1/design-sessions/' + token + '/designs')
      .then(function (data) {
        var versions = renderVersions(data);
        var pending = versions.filter(function (v) { return v.status === 'generating'; });

        if (pending.length && !polling) {
          polling = setInterval(function () {
            api.get('/api/v1/design-sessions/' + token + '/designs')
              .then(function (fresh) {
                var still = renderVersions(fresh).filter(function (v) {
                  return v.status === 'generating';
                });
                if (!still.length) {
                  clearInterval(polling);
                  polling = null;
                }
              })
              .catch(function () { /* transient; the next tick retries */ });
          }, 4000);
        }
      })
      .catch(function (error) { showError(error.message); });
  }

  els.revise.addEventListener('click', function () {
    var instruction = (els.revision.value || '').trim();
    if (!instruction) {
      showError('Please describe the change you would like.');
      return;
    }
    clearError();
    els.revise.disabled = true;
    els.revise.textContent = 'Requesting…';

    api.post('/api/v1/design-sessions/' + token + '/revisions', { instruction: instruction })
      .then(function () {
        els.revision.value = '';
        selected = null;   // show the new version
        return poll();
      })
      .catch(function (error) { showError(error.message); })
      .then(function () {
        els.revise.textContent = 'Request this change';
        els.revise.disabled = false;
      });
  });

  els.approve.addEventListener('click', function () {
    if (!selected || !selected.id) return;
    clearError();
    els.approve.disabled = true;

    api.post('/api/v1/design-sessions/' + token + '/designs/' + selected.id + '/approve', {})
      .then(function () { window.location.href = '/order'; })
      .catch(function (error) {
        showError(error.message);
        els.approve.disabled = false;
      });
  });

  if (!token) {
    window.location.href = '/design';
  } else {
    poll();
  }
})();

/**
 * Backend API helper.
 *
 * The backend URL comes from a data attribute on <body> so one build works in
 * both environments. Errors arrive in the shared envelope
 * {error: {code, message}}, so the customer-facing message is unwrapped here
 * once instead of at every call site.
 */
var api = (function () {
  'use strict';

  var baseUrl = document.body.getAttribute('data-backend-url') || '';

  function request(path, options) {
    var config = Object.assign({ headers: {} }, options || {});
    config.headers['Accept'] = 'application/json';
    if (config.body && !(config.body instanceof FormData)) {
      config.headers['Content-Type'] = 'application/json';
      config.body = JSON.stringify(config.body);
    }

    return fetch(baseUrl + path, config).then(function (response) {
      return response.text().then(function (text) {
        var payload = text ? JSON.parse(text) : null;
        if (!response.ok) {
          var message = (payload && payload.error && payload.error.message) ||
                        'Something went wrong. Please try again.';
          var error = new Error(message);
          error.code = payload && payload.error && payload.error.code;
          error.status = response.status;
          error.details = (payload && payload.error && payload.error.details) || {};
          throw error;
        }
        return payload;
      });
    });
  }

  return {
    get: function (path) { return request(path, { method: 'GET' }); },
    post: function (path, body) { return request(path, { method: 'POST', body: body }); },
    patch: function (path, body) { return request(path, { method: 'PATCH', body: body }); },
    request: request
  };
})();

if (typeof module !== 'undefined' && module.exports) { module.exports = api; }

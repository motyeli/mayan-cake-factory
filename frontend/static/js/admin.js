/**
 * Admin client.
 *
 * The JWT lives in sessionStorage and is sent as a Bearer token. It is a
 * session credential, not a permission: the backend re-checks on every request
 * that the token is valid AND that the account has an active admin profile, so
 * nothing here can grant access by believing it has some.
 */
var admin = (function () {
  'use strict';

  var TOKEN_KEY = 'mayan.admin.token';
  var WHO_KEY = 'mayan.admin.who';

  function token() { return sessionStorage.getItem(TOKEN_KEY); }

  function request(path, options) {
    var config = Object.assign({ headers: {} }, options || {});
    config.headers.Authorization = 'Bearer ' + (token() || '');
    return api.request(path, config).catch(function (error) {
      // An expired or revoked token should return the user to sign-in rather
      // than leaving them staring at a broken page.
      if (error.status === 401) {
        sessionStorage.removeItem(TOKEN_KEY);
        sessionStorage.removeItem(WHO_KEY);
        if (!/\/admin\/login$/.test(window.location.pathname)) {
          window.location.href = '/admin/login';
        }
      }
      throw error;
    });
  }

  function get(path) { return request(path, { method: 'GET' }); }
  function post(path, body) { return request(path, { method: 'POST', body: body }); }
  function patch(path, body) { return request(path, { method: 'PATCH', body: body }); }

  function money(cents, currency) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency: currency || 'USD', minimumFractionDigits: 2
    }).format((cents || 0) / 100);
  }

  function requireSession() {
    if (!token()) {
      window.location.href = '/admin/login';
      return false;
    }
    return true;
  }

  function who() {
    try { return JSON.parse(sessionStorage.getItem(WHO_KEY) || '{}'); }
    catch (e) { return {}; }
  }

  // --------------------------------------------------------------- login

  function mountLogin() {
    var form = document.querySelector('[data-form]');
    var error = document.querySelector('[data-error]');
    var submit = document.querySelector('[data-submit]');

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      error.hidden = true;

      var email = document.getElementById('email').value.trim();
      var password = document.getElementById('password').value;
      if (!email || !password) {
        error.textContent = 'Please enter your email and password.';
        error.hidden = false;
        return;
      }

      submit.disabled = true;
      submit.textContent = 'Signing in…';

      api.post('/api/v1/admin/auth/session', { email: email, password: password })
        .then(function (session) {
          sessionStorage.setItem(TOKEN_KEY, session.access_token);
          sessionStorage.setItem(WHO_KEY, JSON.stringify(session.admin));
          window.location.href = '/admin';
        })
        .catch(function (err) {
          error.textContent = err.message;
          error.hidden = false;
          submit.disabled = false;
          submit.textContent = 'Sign in';
        });
    });
  }

  function signOut() {
    request('/api/v1/admin/auth/session', { method: 'DELETE' })
      .catch(function () { /* signing out locally matters more */ })
      .then(function () {
        sessionStorage.removeItem(TOKEN_KEY);
        sessionStorage.removeItem(WHO_KEY);
        window.location.href = '/admin/login';
      });
  }

  return {
    get: get, post: post, patch: patch,
    money: money, token: token, who: who,
    requireSession: requireSession,
    mountLogin: mountLogin,
    signOut: signOut
  };
})();

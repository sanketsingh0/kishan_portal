/* KisanProcure - shared frontend authentication helpers.
 *
 * Provides a single source of truth for token storage and API authorization
 * across every authenticated page. Never stores passwords.
 */
(function (window) {
  "use strict";

  var TOKEN_KEY = "kp_access_token";
  var REFRESH_KEY = "kp_refresh_token";

  function getAuthToken() {
    return window.localStorage.getItem(TOKEN_KEY) || "";
  }

  function getRefreshToken() {
    return window.localStorage.getItem(REFRESH_KEY) || "";
  }

  function clearTokens() {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_KEY);
  }

  function buildAuthHeaders(extraHeaders) {
    var headers = {};
    var token = getAuthToken();
    if (token) {
      headers["Authorization"] = "Bearer " + token;
    }
    for (var key in (extraHeaders || {})) {
      if (Object.prototype.hasOwnProperty.call(extraHeaders, key)) {
        headers[key] = extraHeaders[key];
      }
    }
    return headers;
  }

  /* Redirect to /login after clearing invalid tokens.
   * Both /login and /register are public pages - never redirect there. */
  function handle401Redirect(nextPath) {
    var isPublicPage =
      window.location.pathname === "/login" ||
      window.location.pathname === "/register";
    if (isPublicPage) {
      return;
    }
    clearTokens();
    var target = "/login";
    if (nextPath) {
      target += "?next=" + encodeURIComponent(nextPath);
    }
    try {
      sessionStorage.setItem("kp_notice", "Session expired. Please login again.");
    } catch (e) { /* ignore */ }
    window.location.href = target;
  }

  /* Fetch wrapper that attaches the bearer token and routes 401 -> login. */
  function authFetch(url, options) {
    options = options || {};
    options.headers = buildAuthHeaders(options.headers || {});
    return fetch(url, options).then(function (res) {
      if (res.status === 401) {
        handle401Redirect(window.location.pathname);
      }
      return res;
    });
  }

  // Backwards-compatible global so existing inline scripts keep working.
  window.getAuthToken = getAuthToken;

  window.KP = {
    getAuthToken: getAuthToken,
    getRefreshToken: getRefreshToken,
    clearTokens: clearTokens,
    buildAuthHeaders: buildAuthHeaders,
    authFetch: authFetch,
    handle401Redirect: handle401Redirect
  };
})(window);
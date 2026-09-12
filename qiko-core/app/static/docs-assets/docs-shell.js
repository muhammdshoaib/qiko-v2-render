// Behaviour for the worker API documentation shell (JM2-1134).
//
// This lives in a file rather than inline in the page for a reason found during security
// review: the application's own SecurityHeadersMiddleware sends "default-src 'self'" with no
// script-src and no 'unsafe-inline'. Caddy replaces that header on preprod and live with a
// policy that does allow inline script, but Caddyfile.dev sets no CSP at all, so in local
// development the application's own header applies and an inline script is blocked outright.
// The page would render and then do nothing, with the failure visible only in the browser
// console. Loading from a file satisfies 'self' under every one of those policies.
//
// It also means the page no longer depends on 'unsafe-inline' being present, so a future
// tightening of the CSP cannot silently break it.
(function () {
  var config = document.getElementById("docs-config");
  var tenant = JSON.parse(config.textContent).tenant;
  var specUrl = "/api/v1/tenants/" + encodeURIComponent(tenant) + "/openapi.json";

  var gate = document.getElementById("gate");
  var error = document.getElementById("error");
  var keyField = document.getElementById("key");
  var envField = document.getElementById("env");
  var warning = document.getElementById("live-warning");

  // The key is deliberately never persisted, not even in sessionStorage. It is a shared
  // service-to-service credential, and the platform CSP permits inline script, so any
  // same-origin XSS would be able to read it back without the holder present. It stays in
  // this closure and dies with the page. The cost is retyping it after a reload.
  function headers() {
    return { "X-Api-Key": keyField.value, "X-Tenant-Id": tenant };
  }

  function refreshWarning() {
    var isLive = envField.value.indexOf("preprod") === -1;
    warning.style.display = isLive ? "block" : "none";
  }

  envField.addEventListener("change", refreshWarning);
  refreshWarning();

  document.getElementById("load").addEventListener("click", function () {
    error.textContent = "";
    if (!keyField.value) {
      error.textContent = "A key is required.";
      return;
    }
    fetch(specUrl, { headers: headers() })
      .then(function (response) {
        if (response.status === 403) {
          throw new Error("That key was rejected.");
        }
        if (!response.ok) {
          throw new Error("Could not load the contract (" + response.status + ").");
        }
        return response.json();
      })
      .then(function (spec) {
        gate.style.display = "none";
        document.getElementById("ui").style.display = "block";
        window.SwaggerUIBundle({
          spec: spec,
          dom_id: "#ui",
          tryItOutEnabled: true,
          // Without this, Swagger UI keeps its default validator.swagger.io reference. No
          // request is made today because the spec is supplied inline rather than by URL,
          // but that is a property of how it is initialised, not a guarantee.
          validatorUrl: null,
          requestInterceptor: function (request) {
            request.headers["X-Api-Key"] = keyField.value;
            request.headers["X-Tenant-Id"] = tenant;
            return request;
          },
        });
      })
      .catch(function (failure) {
        error.textContent = failure.message;
      });
  });
})();

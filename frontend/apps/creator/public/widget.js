/* Qiko embeddable chat widget.
   Usage:
   <script src="https://app.qiko.ai/widget.js"
           data-tenant="acme" data-worker="a1b2c3" data-base="https://app.qiko.ai"></script>
   Injects a floating button that toggles an iframe to the public embed chat. */
(function () {
  var s = document.currentScript;
  var tenant = s.getAttribute("data-tenant");
  var worker = s.getAttribute("data-worker");
  var base = s.getAttribute("data-base") || "";
  if (!tenant || !worker) return;

  var btn = document.createElement("button");
  btn.setAttribute("aria-label", "Open chat");
  btn.style.cssText =
    "position:fixed;bottom:20px;right:20px;width:56px;height:56px;border-radius:9999px;border:0;" +
    "background:#7c5cff;color:#fff;font-size:24px;cursor:pointer;z-index:2147483000;" +
    "box-shadow:0 8px 24px rgba(0,0,0,.2)";
  btn.textContent = "\uD83D\uDCAC";

  var frame = document.createElement("iframe");
  frame.src = base + "/embed/" + encodeURIComponent(tenant) + "/" + encodeURIComponent(worker);
  frame.title = "Qiko chat";
  frame.style.cssText =
    "position:fixed;bottom:88px;right:20px;width:380px;height:560px;max-width:calc(100vw - 40px);" +
    "max-height:calc(100vh - 120px);border:1px solid rgba(0,0,0,.1);border-radius:16px;" +
    "box-shadow:0 16px 48px rgba(0,0,0,.25);z-index:2147483000;display:none;background:#fff";

  var open = false;
  btn.addEventListener("click", function () {
    open = !open;
    frame.style.display = open ? "block" : "none";
    btn.textContent = open ? "\u2715" : "\uD83D\uDCAC";
  });

  document.body.appendChild(frame);
  document.body.appendChild(btn);
})();

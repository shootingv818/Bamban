// ==UserScript==
// @name         Bamban Capture (redacted)
// @namespace    bamban
// @version      0.1.0
// @description  Records your own session's XHR/fetch and exports a REDACTED endpoint map (no secret values). Phone-friendly: load it in a Chromium browser that accepts user scripts (e.g. Quetta), browse, tap the button, send the file.
// @match        *://*/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

/*
 * What this does, and what it deliberately does NOT do:
 *  - It hooks window.fetch and XMLHttpRequest to observe the requests YOUR
 *    browser already makes while you click around. It sends nothing itself.
 *  - On export it writes endpoint_map.json: method + URL (query values and long
 *    digit runs masked), response status/content-type, and the JSON *shape*
 *    (field names kept, every value replaced by its type). No real values,
 *    cookies, tokens, balances or account numbers are ever written out.
 *  - Redaction mirrors bamban/redact.py and is unit-tested with node.
 */
(function () {
  "use strict";

  var MASK = "<redacted>";
  var entries = [];
  var seen = Object.create(null);
  var btn = null;

  // ---- redaction (mirror of bamban/redact.py) ---------------------------
  function redactUrl(raw) {
    try {
      var url = new URL(raw, location.href);
      url.pathname = url.pathname.replace(/\d{5,}/g, MASK);
      var keys = [];
      url.searchParams.forEach(function (_v, k) { keys.push(k); });
      for (var i = 0; i < keys.length; i++) url.searchParams.set(keys[i], MASK);
      return url.toString();
    } catch (e) {
      return String(raw).split("?")[0];
    }
  }

  function shape(v) {
    if (Array.isArray(v)) {
      if (v.length === 0) return [];
      return v.length > 1 ? [shape(v[0]), "... x" + v.length] : [shape(v[0])];
    }
    if (v === null) return "null";
    var t = typeof v;
    if (t === "object") {
      var o = {};
      for (var k in v) if (Object.prototype.hasOwnProperty.call(v, k)) o[k] = shape(v[k]);
      return o;
    }
    if (t === "boolean") return "bool";
    if (t === "number") return "num";
    return "str"; // strings and anything else become an opaque type token
  }

  function shapeJson(text) {
    if (!text) return null;
    try { return shape(JSON.parse(text)); } catch (e) { return "<unparseable-json>"; }
  }

  function record(method, url, status, respCT, respText, reqCT, reqText) {
    respCT = (respCT || "").split(";")[0].trim();
    reqCT = (reqCT || "").split(";")[0].trim();
    var item = {
      method: method || "",
      url: redactUrl(url),
      status: status || 0,
      response_content_type: respCT,
    };
    if (respCT.indexOf("json") !== -1) item.response_shape = shapeJson(respText);
    if (reqCT.indexOf("json") !== -1) item.request_shape = shapeJson(reqText);

    var key = item.method + " " + item.url + " " + item.status;
    if (seen[key]) return;
    seen[key] = true;
    entries.push(item);
    updateBtn();
  }

  // ---- hook fetch -------------------------------------------------------
  var origFetch = window.fetch;
  if (origFetch) {
    window.fetch = function (input, init) {
      var method = "GET", url = "", reqBody = "", reqCT = "";
      try {
        if (typeof input === "string" || input instanceof URL) {
          url = String(input);
          if (init) { method = init.method || "GET"; reqBody = typeof init.body === "string" ? init.body : ""; }
          if (init && init.headers) reqCT = headerOf(init.headers, "content-type");
        } else if (input) {
          url = input.url; method = input.method || "GET";
        }
      } catch (e) {}
      return origFetch.apply(this, arguments).then(function (res) {
        try {
          var ct = res.headers.get("content-type") || "";
          res.clone().text().then(function (t) {
            record(method, url, res.status, ct, t, reqCT, reqBody);
          }, function () {});
        } catch (e) {}
        return res;
      });
    };
  }

  function headerOf(headers, name) {
    try {
      if (typeof headers.get === "function") return headers.get(name) || "";
      for (var k in headers) if (k.toLowerCase() === name) return headers[k];
    } catch (e) {}
    return "";
  }

  // ---- hook XMLHttpRequest ---------------------------------------------
  var OrigOpen = XMLHttpRequest.prototype.open;
  var OrigSend = XMLHttpRequest.prototype.send;
  var OrigSetHeader = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__bam = { method: method, url: url, reqCT: "" };
    return OrigOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
    try {
      if (this.__bam && String(name).toLowerCase() === "content-type") this.__bam.reqCT = value;
    } catch (e) {}
    return OrigSetHeader.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    var self = this;
    try {
      self.addEventListener("load", function () {
        try {
          var ct = self.getResponseHeader("content-type") || "";
          var text = "";
          try {
            if (self.responseType === "" || self.responseType === "text") text = self.responseText;
          } catch (e) {}
          var info = self.__bam || {};
          record(info.method, info.url, self.status, ct, text, info.reqCT || "", typeof body === "string" ? body : "");
        } catch (e) {}
      });
    } catch (e) {}
    return OrigSend.apply(this, arguments);
  };

  // ---- export UI --------------------------------------------------------
  function sortedEntries() {
    return entries.slice().sort(function (a, b) {
      var aj = (a.response_content_type || "").indexOf("json") !== -1 ? 0 : 1;
      var bj = (b.response_content_type || "").indexOf("json") !== -1 ? 0 : 1;
      if (aj !== bj) return aj - bj;
      return a.url < b.url ? -1 : a.url > b.url ? 1 : 0;
    });
  }

  function exportMap() {
    var data = JSON.stringify(sortedEntries(), null, 2);
    var blob = new Blob([data], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "endpoint_map.json";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { a.remove(); URL.revokeObjectURL(a.href); }, 1000);
  }

  function updateBtn() {
    if (btn) btn.textContent = "\u2b07 Bamban (" + entries.length + ")";
  }

  function mkBtn() {
    if (btn) return;
    btn = document.createElement("button");
    btn.textContent = "\u2b07 Bamban (0)";
    var s = btn.style;
    s.position = "fixed"; s.zIndex = "2147483647"; s.bottom = "16px"; s.right = "16px";
    s.padding = "10px 14px"; s.background = "#0a7a5a"; s.color = "#fff"; s.border = "none";
    s.borderRadius = "10px"; s.fontSize = "14px"; s.fontFamily = "sans-serif";
    s.boxShadow = "0 2px 10px rgba(0,0,0,.35)"; s.opacity = "0.9";
    btn.addEventListener("click", exportMap);
    document.body.appendChild(btn);
  }

  if (document.body) mkBtn();
  else document.addEventListener("DOMContentLoaded", mkBtn);
})();

// ==UserScript==
// @name         OTC Relay Bot Executor
// @namespace    local.otc-tracker
// @version      1.1.0
// @description  Pulls bot orders from your relay and clicks Pocket Option controls. Use a public HTTPS relay URL (not 127.0.0.1 / 0.0.0.0).
// @match        *://*.pocketoption.com/*
// @connect      *
// @grant        GM_xmlhttpRequest
// ==/UserScript==

(function () {
  'use strict';

  /** Public base URL only, e.g. https://abc.trycloudflare.com — same as mobile "Relay URL". */
  const RELAY_BASE_URL = '';
  /** Same secret as app "User key" (6+ chars, letters/digits/._- only). */
  const USER_KEY = '';
  /** Optional; must match server RELAY_API_TOKEN if you enabled it. */
  const RELAY_TOKEN = '';

  if (!RELAY_BASE_URL || !USER_KEY) {
    console.warn('[OTC Bot Executor] Set RELAY_BASE_URL and USER_KEY at top of script.');
    return;
  }

  const BASE = String(RELAY_BASE_URL).replace(/\/+$/, '');
  const ORDERS_URL = BASE + '/relay/bot-orders?user_key=' + encodeURIComponent(USER_KEY);
  const RESULT_URL = BASE + '/relay/bot-order-result';
  let lastOrderId = '';
  const busy = new Set();

  function req(method, url, data, cb) {
    const headers = data ? { 'Content-Type': 'application/json' } : { Accept: 'application/json' };
    if (RELAY_TOKEN) headers['X-Relay-Token'] = RELAY_TOKEN;
    GM_xmlhttpRequest({
      method: method,
      url: url,
      headers: headers,
      data: data || undefined,
      onload: function (r) {
        try {
          cb(null, JSON.parse(r.responseText || '{}'));
        } catch (e) {
          cb(e, null);
        }
      },
      onerror: function () {
        cb(new Error('network'), null);
      },
    });
  }

  function postResult(orderId, status, message) {
    req(
      'POST',
      RESULT_URL,
      JSON.stringify({
        user_key: USER_KEY,
        order_id: orderId,
        status: status,
        message: (message || '').slice(0, 300),
        source: 'relay-bot-executor',
      }),
      function () {}
    );
  }

  function visible(el) {
    return el && el.offsetParent !== null;
  }

  function setInputAmount(amount) {
    const candidates = document.querySelectorAll(
      'input[type="number"], input[inputmode="decimal"], input[type="text"]'
    );
    for (let i = 0; i < candidates.length; i++) {
      const el = candidates[i];
      if (!visible(el)) continue;
      const ph = (el.getAttribute('placeholder') || '').toLowerCase();
      const name = (el.getAttribute('name') || '').toLowerCase();
      if (
        ph.indexOf('sum') >= 0 ||
        ph.indexOf('amount') >= 0 ||
        ph.indexOf('invest') >= 0 ||
        name.indexOf('amount') >= 0 ||
        name.indexOf('invest') >= 0
      ) {
        el.focus();
        el.value = String(amount);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
    }
    for (let j = 0; j < candidates.length; j++) {
      const el = candidates[j];
      if (visible(el)) {
        el.focus();
        el.value = String(amount);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
    }
    return false;
  }

  function clickDirection(direction) {
    const put = String(direction || '').toLowerCase() === 'put';
    const sel = put
      ? '[class*="put" i] .fa-arrow-down, .fa-arrow-down, button[class*="put" i], [data-direction="put"]'
      : '[class*="call" i] .fa-arrow-up, .fa-arrow-up, button[class*="call" i], [data-direction="call"]';
    const el = document.querySelector(sel);
    if (el && visible(el)) {
      el.click();
      return true;
    }
    return false;
  }

  function clickBuy() {
    const nodes = document.querySelectorAll('button, a[role="button"], div[role="button"]');
    for (let i = 0; i < nodes.length; i++) {
      const b = nodes[i];
      if (!visible(b)) continue;
      const t = (b.textContent || '').replace(/\s+/g, ' ').trim();
      if (/^buy\b/i.test(t) || /^вложить\b/i.test(t) || /invest/i.test(t)) {
        b.click();
        return true;
      }
    }
    for (let j = 0; j < nodes.length; j++) {
      const b = nodes[j];
      if (!visible(b)) continue;
      const cls = String(b.className || '');
      if (/purchase|deal-submit|place-deal|btn-buy|button-buy/i.test(cls)) {
        b.click();
        return true;
      }
    }
    return false;
  }

  function executeOrder(o) {
    const id = String(o.order_id || '');
    if (!id || busy.has(id)) return;
    busy.add(id);
    const amt = parseFloat(o.amount) || 0;
    const dir = String(o.direction || 'call');
    if (!setInputAmount(amt)) {
      postResult(id, 'failed', 'amount input not found');
      busy.delete(id);
      return;
    }
    window.setTimeout(function () {
      if (!clickDirection(dir)) {
        postResult(id, 'failed', 'direction control not found');
        busy.delete(id);
        return;
      }
      window.setTimeout(function () {
        if (!clickBuy()) {
          postResult(id, 'failed', 'buy button not found');
          busy.delete(id);
          return;
        }
        postResult(id, 'executed', 'click sequence ok');
        window.setTimeout(function () {
          busy.delete(id);
        }, 5000);
      }, 450);
    }, 450);
  }

  function pollOrders() {
    const url = ORDERS_URL + (lastOrderId ? '&since_id=' + encodeURIComponent(lastOrderId) : '');
    req('GET', url, null, function (err, data) {
      if (err || !data || !data.ok) return;
      const orders = data.orders || [];
      if (data.last_order_id) lastOrderId = String(data.last_order_id);
      orders.forEach(function (o) {
        executeOrder(o);
      });
    });
  }

  setInterval(pollOrders, 2500);
  pollOrders();
})();

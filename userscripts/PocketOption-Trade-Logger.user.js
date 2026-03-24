// ==UserScript==
// @name         OTC Tracker — Pocket Option trade logger
// @namespace    local.otc-tracker
// @version      1.1.0
// @description  Sends closed deals only when desktop Collection is ON. Does not POST when tracking is disabled.
// @match        *://*.pocketoption.com/*
// @connect      127.0.0.1
// @connect      *
// @grant        GM_xmlhttpRequest
// ==/UserScript==

(function () {
  'use strict';

  const TRADE_URL = 'http://127.0.0.1:5051/trade-event';
  const STATUS_URL = 'http://127.0.0.1:5051/tracking-status';
  const CLOUD_RELAY_URL = '';
  const CLOUD_RELAY_USER_KEY = '';
  const CLOUD_RELAY_TOKEN = '';

  let lastStatus = { enabled: false, session_id: null };
  let lastSessionId = null;
  const emitted = new Set();
  const pending = new Set();

  function normalizeMoneyText(s) {
    return String(s || '')
      .replace(/[\u2212\u2013\u2014]/g, '-')
      .replace(/[^0-9.\-]/g, '') || '0';
  }

  function rowFingerprint(el) {
    const t = el.innerText.replace(/\s+/g, ' ').trim();
    return t.slice(0, 500);
  }

  function httpJson(method, url, body, cb) {
    const headers = body ? { 'Content-Type': 'application/json' } : {};
    if (CLOUD_RELAY_TOKEN && url.indexOf('/relay/') !== -1) {
      headers['X-Relay-Token'] = CLOUD_RELAY_TOKEN;
    }
    GM_xmlhttpRequest({
      method: method,
      url: url,
      headers: headers,
      data: body || undefined,
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

  function syncBaselineForNewSession() {
    emitted.clear();
    pending.clear();
    document.querySelectorAll('.deals-list__item-short').forEach(function (el) {
      const fp = rowFingerprint(el);
      if (fp) emitted.add(fp);
    });
  }

  function checkStatus(cb) {
    httpJson('GET', STATUS_URL, null, function (err, data) {
      if (err || !data) {
        lastStatus = { enabled: false, session_id: null };
        if (cb) cb(lastStatus);
        return;
      }
      if (!data.enabled) {
        lastSessionId = null;
        emitted.clear();
        pending.clear();
      }
      const sid = data.session_id;
      if (data.enabled && sid && sid !== lastSessionId) {
        lastSessionId = sid;
        syncBaselineForNewSession();
      }
      lastStatus = data;
      if (cb) cb(lastStatus);
    });
  }

  function parseDealRow(el) {
    const assetA = el.querySelector('a');
    const asset = assetA ? assetA.textContent.trim() : '';
    const rows = el.querySelectorAll('.item-row');
    if (rows.length < 2) return null;
    const timeCell = rows[0].querySelectorAll('div');
    const timeText = timeCell.length > 1 ? timeCell[1].textContent.trim() : '';
    const r2 = rows[1].querySelectorAll('div');
    if (r2.length < 3) return null;
    const stakeText = r2[0].textContent || '';
    const payoutText = r2[1].textContent || '';
    const profitText = r2[2].textContent || '';

    const stake = parseFloat(normalizeMoneyText(stakeText)) || 0;
    const payout = parseFloat(normalizeMoneyText(payoutText)) || 0;
    const profit = parseFloat(normalizeMoneyText(profitText)) || 0;

    const up = el.querySelector('.fa-arrow-up');
    const down = el.querySelector('.fa-arrow-down');
    const direction = up ? 'call' : down ? 'put' : '';

    const result = profit > 0 ? 'W' : 'L';

    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    const parts = timeText.split(':');
    const hh = (parts[0] || '00').padStart(2, '0');
    const mm = (parts[1] || '00').padStart(2, '0');
    const closed_at = y + '-' + m + '-' + d + 'T' + hh + ':' + mm + ':00.000Z';

    const trade_id =
      'po|' +
      asset.replace(/\s+/g, ' ') +
      '|' +
      timeText +
      '|' +
      String(stake) +
      '|' +
      String(direction);

    return {
      type: 'trade_closed',
      source: 'firefox-helper',
      asset: asset || 'OTC',
      direction: direction,
      amount: stake,
      duration_sec: null,
      opened_at: null,
      closed_at: closed_at,
      result: result,
      payout: payout,
      profit: profit,
      trade_id: trade_id,
    };
  }

  function postTradeToDesktop(payload, onDone) {
    httpJson('POST', TRADE_URL, JSON.stringify(payload), function (err, respDesktop) {
      if (CLOUD_RELAY_URL && CLOUD_RELAY_USER_KEY) {
        const relayPayload = Object.assign({}, payload, {
          user_key: CLOUD_RELAY_USER_KEY,
          source: 'firefox-helper-relay',
        });
        const relayUrl = String(CLOUD_RELAY_URL).replace(/\/+$/, '') + '/relay/trade-event';
        httpJson('POST', relayUrl, JSON.stringify(relayPayload), function () {
          if (onDone) onDone(err, respDesktop);
        });
      } else {
        if (onDone) onDone(err, respDesktop);
      }
    });
  }

  function processRow(el) {
    const fp = rowFingerprint(el);
    if (!fp || emitted.has(fp) || pending.has(fp)) return;

    checkStatus(function (st) {
      if (!st.enabled) return;
      if (emitted.has(fp) || pending.has(fp)) return;
      const data = parseDealRow(el);
      if (!data || !data.asset) return;
      pending.add(fp);
      postTradeToDesktop(data, function (err, resp) {
        pending.delete(fp);
        if (!err && resp && resp.accepted) {
          emitted.add(fp);
        }
      });
    });
  }

  function scanList() {
    checkStatus(function (st) {
      if (!st.enabled) return;
      document.querySelectorAll('.deals-list__item-short').forEach(function (el) {
        processRow(el);
      });
    });
  }

  const obs = new MutationObserver(function () {
    scanList();
  });
  obs.observe(document.body, { childList: true, subtree: true });

  setInterval(function () {
    checkStatus(null);
  }, 2000);

  scanList();
})();

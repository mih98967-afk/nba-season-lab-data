/* NBA Season Lab v6.9 candidate — private, manually confirmed Sports.ru quotes.
 * The browser never sends these observations to Firestore, GitHub, or analytics.
 * A click is an owner-attested observation, NOT proof of Sports.ru publication
 * time, an independent source audit, a completed transfer, or player eligibility.
 * This module must be loaded before app.js in a future explicitly approved
 * Hosting release. Existing live v6.8 remains untouched.
 */
(function(root, factory) {
  'use strict';
  const api = factory(() => Date.now());
  if (typeof module === 'object' && module.exports) {
    module.exports = {...api, _makeForTests: factory};
  }
  root.NBAPriceEvidence = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function(nowMs) {
  'use strict';
  const KEY = 'nba-season-lab-private-price-evidence-v1';
  const MAX = 500;
  const MAX_PRICE = 20000;
  const ID_RE = /^n[0-9]{3,5}$/;
  const provenance = 'owner_manually_rechecked_sportsru_screen';
  const status = 'private_owner_attested_not_independently_verified';

    const ensure = (okay, code) => {
    if (!okay) throw new Error('PRICE_EVIDENCE_' + code);
  };
  function price(value, field) {
    ensure(value !== null && value !== undefined && String(value).trim() !== '',
           'MISSING_' + field);
    const n = Number(value);
    ensure(Number.isSafeInteger(n) && n >= 0 && n <= MAX_PRICE,
           'INVALID_' + field);
    return n;
  }
  function optionalPrice(value, field) {
    if (value === null || value === undefined || String(value).trim() === '')
      return null;
    return price(value, field);
  }
  function remaining(value) {
    if (value === null || value === undefined || String(value).trim() === '')
      return null;
    const n = Number(value);
    ensure(Number.isInteger(n) && n >= 0 && n <= 3, 'INVALID_QUOTA');
    return n;
  }
  function timestamp(milliseconds) {
    ensure(Number.isSafeInteger(milliseconds)
           && milliseconds >= Date.parse('2026-10-19T00:00:00Z')
           && milliseconds < Date.parse('2027-07-01T00:00:00Z'),
           'INVALID_BROWSER_CLOCK');
    return new Date(milliseconds).toISOString();
  }
  function empty() {
    return {schema_version: 1, private_local_only: true,
            never_autosync: true, source_independently_verified: false,
            restored_from_file_unverified: false, receipts: []};
  }
  function validate(archive) {
    ensure(archive && typeof archive === 'object' && !Array.isArray(archive)
           && archive.schema_version === 1
           && archive.private_local_only === true
           && archive.never_autosync === true
           && archive.source_independently_verified === false
           && (archive.restored_from_file_unverified === undefined ||
               typeof archive.restored_from_file_unverified === 'boolean')
           && Array.isArray(archive.receipts)
           && archive.receipts.length <= MAX, 'CORRUPT_LOCAL_ARCHIVE');
    let prev = 0;
    for (const row of archive.receipts) {
      ensure(row && row.schema_version === 1
             && row.private_local_only === true
             && row.status === status
             && row.provenance === provenance
             && row.user_confirmed_now === true
             && row.source_publication_time_utc === null
             && row.independent_verification === false
             && row.retroactive_quote_claim === false
             && row.transfer_executed === false
             && Array.isArray(row.quotes) && row.quotes.length === 2
             && row.quotes[0].side === 'sell' && row.quotes[1].side === 'buy',
             'CORRUPT_LOCAL_RECEIPT');
      ensure(row.quotes.every(q => ID_RE.test(q.player_id) &&
             Number.isSafeInteger(q.price) &&
             q.price >= 0 && q.price <= MAX_PRICE) &&
             row.quotes[0].player_id !== row.quotes[1].player_id,
             'CORRUPT_LOCAL_PRICE');
      const time = Date.parse(row.observed_at_utc);
      ensure(Number.isFinite(time) && row.observed_at_utc === timestamp(time)
             && time >= prev, 'CORRUPT_OR_BACKDATED_TIME');
      prev = time;
      ensure(row.cash_from_sportsru_screen === null ||
             (Number.isSafeInteger(row.cash_from_sportsru_screen) &&
              row.cash_from_sportsru_screen >= 0 &&
              row.cash_from_sportsru_screen <= MAX_PRICE),
             'CORRUPT_CASH');
      ensure(row.quota_remaining_from_sportsru_screen === null ||
             (Number.isInteger(row.quota_remaining_from_sportsru_screen) &&
              row.quota_remaining_from_sportsru_screen >= 0 &&
              row.quota_remaining_from_sportsru_screen <= 3),
             'CORRUPT_QUOTA');
    }
    return {...archive,
            restored_from_file_unverified: archive.restored_from_file_unverified === true};
  }
  function read(storage) {
    ensure(storage && typeof storage.getItem === 'function', 'NO_LOCAL_STORAGE');
    const raw = storage.getItem(KEY);
    if (raw === null) return empty();
    let parsed;
    try { parsed = JSON.parse(raw); }
    catch { throw new Error('PRICE_EVIDENCE_CORRUPT_LOCAL_ARCHIVE'); }
    return validate(parsed);
  }
  function capture(storage, data) {
    ensure(data && typeof data === 'object' && data.userConfirmedNow === true,
           'EXPLICIT_CONFIRMATION_REQUIRED');
    const out = data.outId, incoming = data.inId;
    ensure(typeof out === 'string' && typeof incoming === 'string'
           && ID_RE.test(out) && ID_RE.test(incoming) && out !== incoming,
           'INVALID_PLAYER_PAIR');
    // Values must come from separate, BLANK user-confirmation fields.
    // Never accept estimated app inputs as a source without manual re-entry.
    const sell = price(data.confirmedSellPrice, 'SELL_QUOTE');
    const buy = price(data.confirmedBuyPrice, 'BUY_QUOTE');
    const cash = optionalPrice(data.confirmedCash, 'CASH');
    const quota = remaining(data.confirmedQuota);
    const at = timestamp(nowMs());
    const archive = read(storage);
    ensure(archive.receipts.length < MAX, 'ARCHIVE_FULL_EXPORT_FIRST');
    const latest = archive.receipts.at(-1);
    ensure(!latest || Date.parse(at) >= Date.parse(latest.observed_at_utc),
           'CLOCK_BACKWARDS');
    const receipt = {
      schema_version: 1, status, private_local_only: true,
      user_confirmed_now: true, provenance,
      observed_at_utc: at, source_publication_time_utc: null,
      independent_verification: false,
      first_observation_is_owner_click_not_platform_timestamp: true,
      retroactive_quote_claim: false, transfer_executed: false,
      quotes: [{side: 'sell', player_id: out, price: sell},
               {side: 'buy', player_id: incoming, price: buy}],
      cash_from_sportsru_screen: cash,
      quota_remaining_from_sportsru_screen: quota,
      quota_reset_rule_verified: false,
      lock_state_verified: false,
      complete_future_market_price_coverage: false,
      model_estimated_prices_used: false,
      safe_for_automatic_optimization: false
    };
    const next = {...archive, receipts: [...archive.receipts, receipt]};
    validate(next);
    // Do NOT call app.save(), nbaCloudSave(), fetch(), or any remote service.
    try { storage.setItem(KEY, JSON.stringify(next)); }
    catch { throw new Error('PRICE_EVIDENCE_STORAGE_WRITE_FAILED'); }
    return JSON.parse(JSON.stringify(receipt));
  }
  function exportData(storage) {
    // User must explicitly request a download. Never silently export.
    return JSON.parse(JSON.stringify(read(storage)));
  }
  function importData(storage, imported, explicit) {
    ensure(explicit === true, 'EXPLICIT_IMPORT_CONFIRMATION_REQUIRED');
    // A restore can never authenticate the timestamp of the original observation.
    const checked = validate(JSON.parse(JSON.stringify(imported)));
    const now = nowMs();
    ensure(checked.receipts.every(r => Date.parse(r.observed_at_utc) <= now),
           'FUTURE_IMPORTED_OBSERVATION');
    const restored = {...checked, restored_from_file_unverified: true};
    try { storage.setItem(KEY, JSON.stringify(restored)); }
    catch { throw new Error('PRICE_EVIDENCE_STORAGE_WRITE_FAILED'); }
    return restored.receipts.length;
  }
  function erase(storage, explicit) {
    ensure(explicit === true, 'EXPLICIT_ERASE_CONFIRMATION_REQUIRED');
    storage.removeItem(KEY);
  }
  return {KEY, read, capture, exportData, importData, erase,
          get status() { return status; }};
});

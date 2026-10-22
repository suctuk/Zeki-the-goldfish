/**
 * Zeki community ideas: Google Form -> Sheet -> this script -> JSON for the ESP32.
 *
 * Install (see zeki-build-spec.md, Day 4):
 *   1. In the Sheet linked to the Form: Extensions > Apps Script, paste this file, save.
 *   2. Run setup() once and approve the permissions.
 *   3. Deploy > New deployment > Web app. Execute as: Me. Who has access: Anyone.
 *      Copy the /exec URL into secrets.py (APPS_SCRIPT_URL).
 *
 * What it does:
 *   - Adds three columns to the responses sheet: Flagged | Approved | Id.
 *   - On every form submit: checks idea + name for links, email addresses,
 *     phone numbers and @handles, then against the Blocklist tab.
 *     Flagged = the reason (e.g. "link", "word: xxx"), or "no".
 *     MODE "demo"   -> clean submissions are approved automatically.
 *     MODE "review" -> nothing is approved until you set Approved = yes.
 *   - Approved is a dropdown: "yes" (Zeki shows it), "no" (rejected), or
 *     blank (waiting for review; counted in "N to review").
 *   - Id is assigned when a row is APPROVED (not when submitted), so a row you
 *     approve by hand later still gets a new, higher Id and Zeki picks it up.
 *   - doGet(?since=N) returns approved rows with Id > N as JSON, oldest first,
 *     max 5, text trimmed, plus "pending": how many submissions still wait for
 *     your review (Zeki shows "N to review"). The device polls this every 30 s.
 *
 *   - Burst alert: when ALERT_COUNT submissions arrive within ALERT_WINDOW_MIN,
 *     emails you a link to the Sheet (then stays quiet for ALERT_COOLDOWN_MIN).
 *
 * Toggle modes from the editor: run setDemoMode() or setReviewMode().
 * Override anything by hand: set Approved to yes / no. "no" hides it from Zeki.
 */

const MAX_TEXT = 120;
const MAX_NAME = 20;
const MAX_PER_POLL = 5;
const BLOCKLIST_URL = 'https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/en';
const BLOCKLIST_SHEET = 'Blocklist';
const EXTRA_COLS = ['Flagged', 'Approved', 'Id'];

// Burst alert: email when this many submissions arrive within the window.
const ALERT_COUNT = 4;
const ALERT_WINDOW_MIN = 60;
const ALERT_COOLDOWN_MIN = 60;
const ALERT_EMAIL = '';          // '' = the account that owns this script

// Form answer labels -> Zeki's tags. Must match the Form options exactly, and
// the tag values must match config.QUESTIONS on the device.
const TIME_MAP = {'15 min': '15min', 'An afternoon': 'afternoon', 'A weekend': 'weekend'};
const DOES_MAP = {'Sense': 'sense', 'Show': 'show', 'Move': 'move', 'Make noise': 'noise', 'Go online': 'online'};
const VIBE_MAP = {'Useful': 'useful', 'Silly': 'silly', 'Wearable': 'wearable', 'Desk toy': 'desk'};

// ---------------------------------------------------------------- setup ----

function setup() {
  const sheet = responsesSheet_();
  const ss = sheet.getParent();

  // Helper columns at the end of the responses sheet.
  let headers = headerRow_(sheet);
  EXTRA_COLS.forEach(function (name) {
    if (headers.indexOf(name) === -1) {
      const col = sheet.getLastColumn() + 1;
      if (col > sheet.getMaxColumns()) sheet.insertColumnAfter(sheet.getMaxColumns());
      sheet.getRange(1, col).setValue(name).setFontWeight('bold');
      headers = headerRow_(sheet);
    }
  });

  importBlocklist();

  const props = props_();
  if (!props.getProperty('MODE')) props.setProperty('MODE', 'demo');
  if (!props.getProperty('NEXT_ID')) props.setProperty('NEXT_ID', '1');

  const hasTrigger = ScriptApp.getProjectTriggers().some(function (t) {
    return t.getHandlerFunction() === 'onFormSubmit';
  });
  if (!hasTrigger) ScriptApp.newTrigger('onFormSubmit').forSpreadsheet(ss).onFormSubmit().create();

  // Process any responses that arrived before setup.
  for (let r = 2; r <= sheet.getLastRow(); r++) processRow_(sheet, r);

  Logger.log('Setup done. Mode: ' + props.getProperty('MODE') + '. Next Id: ' + props.getProperty('NEXT_ID'));
}

function importBlocklist() {
  const ss = SpreadsheetApp.getActive();
  let tab = ss.getSheetByName(BLOCKLIST_SHEET);
  if (!tab) {
    tab = ss.insertSheet(BLOCKLIST_SHEET);
    tab.getRange('A1:B1').setValues([['LDNOOBW list (imported, re-run importBlocklist to refresh)',
                                       'Custom terms (add your own, one per cell)']]).setFontWeight('bold');
  }
  const words = UrlFetchApp.fetch(BLOCKLIST_URL).getContentText()
    .split('\n').map(function (w) { return w.trim(); }).filter(function (w) { return w; });
  if (tab.getMaxRows() > 1) tab.getRange(2, 1, tab.getMaxRows() - 1, 1).clearContent();
  if (tab.getMaxRows() < words.length + 1) tab.insertRowsAfter(tab.getMaxRows(), words.length + 1 - tab.getMaxRows());
  tab.getRange(2, 1, words.length, 1).setValues(words.map(function (w) { return [w]; }));
  Logger.log('Imported ' + words.length + ' blocklist terms.');
}

function setDemoMode() { props_().setProperty('MODE', 'demo'); Logger.log('MODE = demo'); }
function setReviewMode() { props_().setProperty('MODE', 'review'); Logger.log('MODE = review'); }

// ------------------------------------------------------------- triggers ----

function onFormSubmit(e) {
  const sheet = e.range.getSheet();
  try {
    healRecent_(sheet);   // older rows a Google hiccup skipped first, so Ids stay in order
  } finally {
    try {
      processRow_(sheet, e.range.getRow());   // no-op if healRecent_ already did it; throws if it can't
    } finally {
      try { burstAlert_(sheet); } catch (err) { Logger.log('burst alert failed: ' + err); }
    }
  }
}

// Last 25 rows: redo any that never got a Flagged value, and give an Id to
// any approved row missing one (a hiccup between approving and numbering).
function healRecent_(sheet) {
  const c = columns_(sheet);
  const last = sheet.getLastRow();
  const first = Math.max(2, last - 24);
  if (!c.flagged || last < first) return;
  const n = last - first + 1;
  const flags = sheet.getRange(first, c.flagged, n, 1).getValues();
  const appr = sheet.getRange(first, c.approved, n, 1).getValues();
  const ids = sheet.getRange(first, c.id, n, 1).getValues();
  for (let i = 0; i < n; i++) {
    try {
      if (flags[i][0] === '') processRow_(sheet, first + i);
      else if (approved_(appr[i][0]) && ids[i][0] === '') assignId_(sheet, first + i, c);
    } catch (err) {
      Logger.log('row ' + (first + i) + ' failed: ' + err);
    }
  }
}

// Simple trigger: setting Approved = yes by hand assigns the row an Id.
function onEdit(e) {
  const sheet = e.range.getSheet();
  if (!sheet.getFormUrl()) return;
  const c = columns_(sheet);
  if (!c.approved || e.range.getColumn() > c.approved || e.range.getLastColumn() < c.approved) return;
  for (let r = Math.max(2, e.range.getRow()); r <= e.range.getLastRow(); r++) {
    if (approved_(sheet.getRange(r, c.approved).getValue())) assignId_(sheet, r, c);
  }
}

// ---------------------------------------------------------------- device ----

function doGet(e) {
  const since = Number((e && e.parameter && e.parameter.since) || 0);
  const sheet = responsesSheet_();
  const c = columns_(sheet);
  const out = [];
  let pending = 0;
  const n = sheet.getLastRow() - 1;
  if (n > 0 && c.idea && c.approved && c.id) {
    sheet.getRange(2, 1, n, sheet.getLastColumn()).getValues().forEach(function (r) {
      if (String(r[c.approved - 1]).trim() === '' && String(r[c.idea - 1]).trim()) pending++;
      const id = Number(r[c.id - 1]);
      if (!approved_(r[c.approved - 1]) || !(id > since)) return;
      out.push({
        id: id,
        text: clip_(r[c.idea - 1], MAX_TEXT),
        name: c.name ? clip_(r[c.name - 1], MAX_NAME) : '',
        time: c.time ? (TIME_MAP[String(r[c.time - 1]).trim()] || '') : '',
        does: c.does ? tags_(r[c.does - 1], DOES_MAP) : [],
        vibe: c.vibe ? tags_(r[c.vibe - 1], VIBE_MAP) : []
      });
    });
  }
  out.sort(function (a, b) { return a.id - b.id; });
  return ContentService.createTextOutput(JSON.stringify({ideas: out.slice(0, MAX_PER_POLL), pending: pending}))
    .setMimeType(ContentService.MimeType.JSON);
}

// Run from the editor to see what Zeki would get.
function testDoGet() {
  Logger.log(doGet({parameter: {since: '0'}}).getContent());
}

// -------------------------------------------------------------- helpers ----

function responsesSheet_() {
  const ss = SpreadsheetApp.getActive();
  if (!ss) throw new Error('This script is not attached to a spreadsheet. Open the "Zeki ideas" Sheet ' +
                           '(not the Form) and use Extensions > Apps Script there.');
  const s = ss.getSheets().filter(function (sh) { return sh.getFormUrl(); })[0];
  if (!s) throw new Error('No form-linked sheet. In the Form: Responses > Link to Sheets, then open that Sheet.');
  return s;
}

function headerRow_(sheet) {
  return sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(function (h) { return String(h).trim(); });
}

// 1-based column numbers (0 = missing). Form questions are matched by how
// their titles START, so small wording changes after that are fine.
function columns_(sheet) {
  const h = headerRow_(sheet);
  const lower = h.map(function (x) { return x.toLowerCase(); });
  function starts(prefix) { return lower.findIndex(function (x) { return x.indexOf(prefix) === 0; }) + 1; }
  return {
    idea: starts('your idea'), name: starts('your name'), time: starts('how long'),
    does: starts('what does'), vibe: starts('vibe'),
    flagged: h.indexOf('Flagged') + 1, approved: h.indexOf('Approved') + 1, id: h.indexOf('Id') + 1
  };
}

function processRow_(sheet, row) {
  const c = columns_(sheet);
  if (!c.flagged || !c.approved || !c.id) throw new Error('Run setup() first.');
  const flagCell = sheet.getRange(row, c.flagged);
  if (flagCell.getValue() !== '') return;               // already processed
  const idea = String(sheet.getRange(row, c.idea).getValue());
  const name = c.name ? String(sheet.getRange(row, c.name).getValue()) : '';
  const word = badWord_(idea + ' ' + name);
  const hit = contactInfo_(idea + ' ' + name) || (word ? 'word: ' + word : '');
  const demo = props_().getProperty('MODE') === 'demo';  // storage read BEFORE any write
  const approvedCell = sheet.getRange(row, c.approved);
  approvedCell.setDataValidation(SpreadsheetApp.newDataValidation()
    .requireValueInList(['yes', 'no'], true).setAllowInvalid(false).build());
  if (demo && !hit && idea.trim()) {
    approvedCell.setValue('yes');
    assignId_(sheet, row, c);
  }
  // Flagged is the "done" marker, so it's written LAST: if anything above
  // fails, the row is redone in full by healRecent_() or setup().
  flagCell.setValue(hit || 'no');
}

function assignId_(sheet, row, c) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const idCell = sheet.getRange(row, c.id);
    if (idCell.getValue() !== '') return;               // keeps its Id if re-approved
    const props = props_();
    const id = Number(props.getProperty('NEXT_ID') || '1');
    idCell.setValue(id);
    props.setProperty('NEXT_ID', String(id + 1));
  } finally {
    lock.releaseLock();
  }
}

// --- resilience ----------------------------------------------------------
// Google's storage and mail services occasionally fail with transient errors
// (e.g. "server error occurred while reading from storage. DEADLINE_EXCEEDED").
// Retry those a few times instead of losing a submission.

const TRANSIENT_RE = /DEADLINE_EXCEEDED|server error|timed out|try again|Service invoked too many times|unavailable/i;

function retry_(fn) {
  for (let attempt = 1; ; attempt++) {
    try {
      return fn();
    } catch (err) {
      if (attempt >= 3 || !TRANSIENT_RE.test(String(err))) throw err;
      Logger.log('transient error, retry ' + attempt + ': ' + err);
      Utilities.sleep(1500 * attempt);
    }
  }
}

function props_() {
  const p = retry_(function () { return PropertiesService.getScriptProperties(); });
  return {
    getProperty: function (k) { return retry_(function () { return p.getProperty(k); }); },
    setProperty: function (k, v) { return retry_(function () { return p.setProperty(k, v); }); },
    deleteProperty: function (k) { return retry_(function () { return p.deleteProperty(k); }); }
  };
}

function sendMail_(to, subject, body) {
  return retry_(function () { return MailApp.sendEmail(to, subject, body); });
}

function approved_(v) {
  return v === true || String(v).trim().toLowerCase() === 'yes';
}

function clip_(v, max) {
  const s = String(v).replace(/\s+/g, ' ').trim();
  return s.length <= max ? s : s.slice(0, max - 3).replace(/\s+\S*$/, '') + '...';
}

function tags_(cell, map) {
  return String(cell).split(',').map(function (s) { return map[s.trim()]; }).filter(function (t) { return t; });
}

// --- burst alert -----------------------------------------------------------

function burstAlert_(sheet) {
  const props = props_();
  const now = Date.now();
  const last = Number(props.getProperty('LAST_ALERT') || 0);
  if (now - last < ALERT_COOLDOWN_MIN * 60000) return;
  const n = sheet.getLastRow() - 1;
  if (n < ALERT_COUNT) return;
  const c = columns_(sheet);
  const take = Math.min(n, 50);                       // recent rows are at the bottom
  const rows = sheet.getRange(sheet.getLastRow() - take + 1, 1, take, sheet.getLastColumn()).getValues();
  const recent = rows.filter(function (r) {
    const ts = new Date(r[0]).getTime();           // Date object or text timestamp
    return !isNaN(ts) && now - ts <= ALERT_WINDOW_MIN * 60000;
  });
  if (recent.length < ALERT_COUNT) return;
  props.setProperty('LAST_ALERT', String(now));
  const pending = recent.filter(function (r) { return String(r[c.approved - 1]).trim() === ''; }).length;
  const lines = recent.slice(-10).map(function (r) {
    const flag = String(r[c.flagged - 1]);
    return '- ' + clip_(r[c.idea - 1], MAX_TEXT) + (flag && flag !== 'no' ? '   [flagged: ' + flag + ']' : '');
  });
  const url = sheet.getParent().getUrl() + '#gid=' + sheet.getSheetId();
  const body = [
    recent.length + ' ideas arrived in the last ' + ALERT_WINDOW_MIN + ' minutes (' + pending +
      ' waiting for review). Mode: ' + props.getProperty('MODE') + '.',
    '',
    'Open the sheet: ' + url,
    '',
    'Latest:'
  ].concat(lines, ['', 'Next alert at the earliest in ' + ALERT_COOLDOWN_MIN + ' minutes.']);
  sendMail_(ALERT_EMAIL || Session.getEffectiveUser().getEmail(),
    'Zeki: ' + recent.length + ' new ideas in the last hour', body.join('\n'));
}

// Run from the editor to send yourself a sample alert (ignores the thresholds).
function testAlert() {
  props_().deleteProperty('LAST_ALERT');
  const sheet = responsesSheet_();
  sendMail_(ALERT_EMAIL || Session.getEffectiveUser().getEmail(), 'Zeki: test alert',
    'Alerts work. Sheet: ' + sheet.getParent().getUrl());
  Logger.log('Test alert sent.');
}

// --- moderation ------------------------------------------------------------

// Links, emails, phone numbers and @handles: the usual spam / doxxing pattern
// on open forms. Runs on the RAW text (normalize_ would strip "@" and ".").
// Phone = 10+ digits in one run of digits/spaces/dashes/dots/parens, so part
// numbers, voltages and dates ("3.3V", "2026-10-21", "SEN-15805") pass.
const LINK_RE = /(https?:\/\/|\bwww\.|\b[a-z0-9-]+\.(com|net|org|io|ly|co|me|gg|xyz|app|dev|info|biz|us|uk|ca|tv|link|site|online|shop|store|blog|page|ai)\b)/i;
const EMAIL_RE = /[^\s@]+@[^\s@]+\.[a-z]{2,}/i;
const HANDLE_RE = /(^|[\s(])@[a-z0-9_.]{2,}/i;
const PHONE_RUN_RE = /\+?\d[\d\s().-]{6,}\d/g;

function contactInfo_(text) {
  const s = String(text);
  if (EMAIL_RE.test(s)) return 'email';
  if (LINK_RE.test(s)) return 'link';
  if (HANDLE_RE.test(s)) return '@handle';
  const runs = s.match(PHONE_RUN_RE) || [];
  for (let i = 0; i < runs.length; i++) {
    if (runs[i].replace(/\D/g, '').length >= 10) return 'phone';
  }
  return '';
}

// Normalize: lowercase, common leetspeak -> letters, punctuation -> spaces.
// Single words match whole tokens only (no "Scunthorpe" false positives);
// multi-word terms match as phrases. Stretched words ("baaaad") are caught by
// squeezing runs of 3+ letters. The Approved column is the real safety net.

const LEET = {'0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '@': 'a', '$': 's'};

function normalize_(s) {
  return String(s).toLowerCase()
    .replace(/[01345@$]/g, function (ch) { return LEET[ch]; })
    .replace(/[^a-z]+/g, ' ').trim();
}

function blockTerms_() {
  const tab = SpreadsheetApp.getActive().getSheetByName(BLOCKLIST_SHEET);
  if (!tab || tab.getLastRow() < 2) return [];
  return tab.getRange(2, 1, tab.getLastRow() - 1, 2).getValues()
    .reduce(function (all, row) { return all.concat(row); }, [])
    .map(normalize_).filter(function (t) { return t; });
}

function badWord_(text) {
  const norm = normalize_(text);
  if (!norm) return '';
  const padded = ' ' + norm + ' ';
  const tokens = norm.split(' ');
  const squeezed2 = tokens.map(function (t) { return t.replace(/(.)\1{2,}/g, '$1$1'); });
  const squeezed1 = tokens.map(function (t) { return /(.)\1{2,}/.test(t) ? t.replace(/(.)\1+/g, '$1') : null; });
  const terms = blockTerms_();
  for (let i = 0; i < terms.length; i++) {
    const t = terms[i];
    if (t.indexOf(' ') !== -1) {
      if (padded.indexOf(' ' + t + ' ') !== -1) return t;
    } else if (tokens.indexOf(t) !== -1 || squeezed2.indexOf(t) !== -1 ||
               squeezed1.indexOf(t.replace(/(.)\1+/g, '$1')) !== -1) {
      return t;
    }
  }
  return '';
}

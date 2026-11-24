#!/usr/bin/env python3
"""life-page v2: regenerate the single unified status page (/srv/status/index.html).

Sections (life first, infra second):
  Open Commitments | School Upcoming | School Recent Posts | Captures |
  Email Highlights | Recurring Senders | Systems (infra cells)
Replaces the old two-page (index + life.html) split.
"""
import html
import json
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOK = open('/home/ben/.hermes-secrets/fastmail-rw-token').read().strip()
HOME = '/home/ben'
OUT = '/srv/status/index.html'
TEMPLATE = f'{HOME}/bin/life_template.html'
HKT = timezone(timedelta(hours=8))


def jmap(calls):
    b = json.dumps({'using': ['urn:ietf:params:jmap:mail'], 'methodCalls': calls}).encode()
    r = urllib.request.Request('https://api.fastmail.com/jmap/api/', data=b, method='POST')
    r.add_header('Authorization', 'Bearer ' + TOK)
    r.add_header('Content-Type', 'application/json')
    return json.loads(urllib.request.urlopen(r, timeout=60).read().decode())


def commitments():
    p = Path(f'{HOME}/life/commitments.md')
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        m = re.match(r'- \[ \] \(added (\d{4}-\d{2}-\d{2})\) (.*)', line.strip())
        if m:
            added, text = m.group(1), m.group(2)
            parts = text.split(' — ', 1)
            main = html.escape(parts[0].strip())
            note = html.escape(parts[1].strip()) if len(parts) > 1 else ''
            disp = main + (f' <span class="muted">({note})</span>' if note else '')
            out.append({'text': disp})
    return out[:20]


UPCOMING_PATTERNS = re.compile(
    r'(deadline|by (monday|tuesday|wednesday|thursday|friday|saturday|sunday)|'
    r'close[sd]? on|closes \w+ \d|sign[- ]?up|enrol|remind|invitation|'
    r'\d{1,2} (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|'
    r'(january|february|march|april|june|july|august|september|october|november|december) \d{1,2}|'
    r'celebration|performance|pantomime|fair|sale|morning|webinar|event)', re.I)


EVENT_DATE = re.compile(
    r'(?:(mon|tues|wednes|thurs|fri|satur|sun)day\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+'
    r'(january|february|march|april|may|june|july|august|september|october|november|december)'
    r'(?:\s+(\d{4}))?(?:\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)))?', re.I)


def extract_event_date(text, received):
    """Pull the event date out of a school mail body. Returns 'dd Mon' or None.
    Looks for explicit dates in the future relative to received date."""
    try:
        recv = datetime.fromisoformat(received.replace('Z', '+00:00')).astimezone(HKT)
    except Exception:
        recv = datetime.now(HKT)
    MONTHS = {m[:3]: i for i, m in enumerate(
        ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
         'September', 'October', 'November', 'December'], start=1)}
    best_dt = None
    best_label = None
    for m in EVENT_DATE.finditer(text or ''):
        day = int(m.group(2))
        mon = m.group(3)[:3].title()
        if mon not in MONTHS:
            continue
        year = int(m.group(4)) if m.group(4) else recv.year
        if not m.group(4) and (MONTHS[mon] < recv.month or (MONTHS[mon] == recv.month and int(m.group(2)) < recv.day)):
            year += 1  # event must be upcoming: roll to next year
        try:
            dt = datetime(year, MONTHS[mon], day, tzinfo=HKT)
        except ValueError:
            continue
        today = datetime.now(HKT).date()
        if dt.date() < today - timedelta(days=2):
            continue  # event already passed
        label = dt.strftime('%d %b')
        if m.group(5):
            label += ' ' + m.group(5).strip().upper()
        if best_dt is None or dt < best_dt:
            best_dt, best_label = dt, label
    return best_label


def school_upcoming():
    """Scan School mailboxes for event-ish subjects; extract event dates from bodies."""
    try:
        lookback = (datetime.now(HKT) - timedelta(days=21)).strftime('%Y-%m-%d')
        out = subprocess.run(
            ['/home/ben/.local/bin/fm', 'search', '--from', 'shrewsbury',
             '--after', lookback, '--limit', '60', '--format', 'json'],
            capture_output=True, text=True, timeout=120).stdout
        out2 = subprocess.run(
            ['/home/ben/.local/bin/fm', 'search', '--from', 'pips.edu.hk',
             '--after', lookback, '--limit', '60', '--format', 'json'],
            capture_output=True, text=True, timeout=120).stdout
        emails = json.loads(out).get('emails', []) + json.loads(out2).get('emails', [])
    except Exception:
        return []
    seen = set()
    rows = []
    for e in emails:
        subj = re.sub(r'^\[.*?\]\s*', '', e.get('subject', '') or '').strip()
        if not UPCOMING_PATTERNS.search(subj):
            continue
        if re.search(r'tuition|fees? for|invoice|payment (due|reminder)', subj, re.I):
            continue
        base = re.sub(r'^reminder:?\s*', '', subj, flags=re.I)
        base = re.sub(r'\s*-\s*REMINDER\s*$', '', base, flags=re.I)
        key = re.sub(r'[^a-z0-9]', '', base.lower())[:40]
        if key in seen:
            continue
        seen.add(key)
        subj = base
        # fetch body to find the event date (limit: only first 12 candidates)
        if len(rows) < 12:
            body = ''
            try:
                body = subprocess.run(['/home/ben/.local/bin/fm', 'read', e['id'], '--format', 'text'],
                                      capture_output=True, text=True, timeout=60).stdout
            except Exception:
                pass
            event = extract_event_date(body, e.get('received_at', ''))
            try:
                recv = datetime.fromisoformat(e['received_at'].replace('Z', '+00:00')).astimezone(HKT)
            except Exception:
                recv = datetime.now(HKT)
            if not event:
                continue  # upcoming list = only real dated events
            when = event
            rows.append({'when': when, 'text': html.escape(subj[:90]),
                         'event': True})
    # sort: rows with real event dates first by date, then reminders
    def sort_key(r):
        w = r['when']
        try:
            mm = re.search(r'(\d{1,2})\s+([A-Za-z]{3})(?:\s+(\d{1,2})(?::(\d{2}))?\s*(AM|PM))?', w)
            if not mm:
                raise ValueError(w)
            day = int(mm.group(1))
            mon = mm.group(2)[:3].title()
            months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            year = datetime.now(HKT).year
            dt = datetime(year, months.index(mon) + 1, day, tzinfo=HKT)
            if mm.group(3):
                hh = int(mm.group(3)) % 12
                if (mm.group(5) or 'AM').upper() == 'PM':
                    hh += 12
                dt = dt.replace(hour=hh, minute=int(mm.group(4) or 0))
            return (0, dt)
        except Exception:
            return (1, datetime.now(HKT))
    rows.sort(key=sort_key)
    return rows[:8]


def school_posts():
    try:
        out = subprocess.run(['/home/ben/bin/seesaw-fetch.py', '--since-hours', '168'],
                             capture_output=True, text=True, timeout=300).stdout
    except Exception:
        return []
    items = []
    for line in out.splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        items.append({'date': d.get('date', '?'), 'text': d.get('text'), 'images': len(d.get('images') or []), 'klass': 'Seesaw'})
    return items[:15]


def captures():
    """Saved Messages captures - the sweep agent appends
    '- [YYYY-MM-DD HH:MM] text' lines to ~/life/captures.md; we display them."""
    p = Path(f'{HOME}/life/captures.md')
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        m = re.match(r'- \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\] (.*)', line.strip())
        if m:
            rows.append({'when': m.group(1)[5:10], 'text': html.escape(m.group(2))})
    return rows[:10]


def email_highlights():
    try:
        lookback = (datetime.now(HKT) - timedelta(days=7)).strftime('%Y-%m-%d')
        out = subprocess.run(['/home/ben/.local/bin/fm', 'search', '--after', lookback,
                              '--limit', '100', '--format', 'json'],
                             capture_output=True, text=True, timeout=120).stdout
        emails = json.loads(out).get('emails', [])
    except Exception:
        return []
    SKIP = re.compile(r'seesaw|linkedin|uber|pips.edu.hk|mailer\.humblebundle|patreon|substack|kagi subscription', re.I)
    NOISE_HL = re.compile(r'run (failed|succeeded)|ci |workflow|transaction notification|交易通知|statement|e-advice|direct debit|credit note', re.I)
    WANT = re.compile(r'failed payment|payment failed|invoice (overdue|unpaid)|expire|sign[- ]?up (open|now)|form|deadline|fee|permission|invitation|reminder', re.I)
    rows = []
    seen = set()
    for e in emails:
        subj = re.sub(r'^\[.*?\]\s*', '', (e.get('subject', '') or '')).strip()
        frm = (e.get('from') or [{}])[0].get('email', '')
        if SKIP.search(frm) or NOISE_HL.search(subj):
            continue
        if not WANT.search(subj):
            continue
        key = subj.lower()[:40]
        if key in seen:
            continue
        seen.add(key)
        try:
            dt = datetime.fromisoformat(e['received_at'].replace('Z', '+00:00')).astimezone(HKT)
        except Exception:
            continue
        rows.append({'when': dt.strftime('%d %b'), 'text': html.escape(subj[:90])})
    return rows[:6]


def recurring():
    """Real subscriptions: vendors with RECENT billing/receipt mail (active)
    surfaced for review; heavy marketing-only vendors as unsubscribe candidates."""
    p = Path(f'{HOME}/life/subscriptions-vendors.csv')
    if not p.exists():
        return []
    PAY = re.compile(r'stripe|kagi|apple|google play|sony|playstation|nintendo|'
                     r'jetbrains|bitwarden|github|namecheap|digitalocean|icloud|'
                     r'netflix|spotify|youtube|fastmail|godaddy', re.I)
    rows = []
    for line in p.read_text().splitlines()[2:]:
        vendor, rec_s, bil_s, news_s = [x.strip() for x in line.split(',')]
        rec, bil, news = int(rec_s), int(bil_s), int(news_s)
        if 'humblebundle' in vendor or 'foodpanda' in vendor or 'linkedin' in vendor:
            continue  # known unsubscribed / one-off
        if PAY.search(vendor) or bil:
            note = f'paid: {rec} receipts' + (f', {bil} billing alerts' if bil else '')
            rows.append({'vendor': html.escape(vendor), 'note': note})
        elif news > 20:
            rows.append({'vendor': html.escape(vendor), 'note': f'marketing: {news} mails - unsubscribe?'})
    return rows[:12]


def infra():
    cells = []
    # read watchdog state file if present
    wf = Path('/home/ben/.watchdog-state')
    state = 'ok'
    try:
        txt = wf.read_text()
        state = 'ok' if 'ok' in txt.lower() or '0' in txt else 'warn'
    except Exception:
        pass
    disk = subprocess.run(['df', '-h', '/'], capture_output=True, text=True).stdout.splitlines()[-1].split()
    mem = subprocess.run(['free', '-m'], capture_output=True, text=True).stdout.splitlines()[1].split()
    disk_pct = disk[4]
    mem_pct = f"{int(mem[2]) * 100 // int(mem[1])}%"
    def vcls(p):
        try:
            return 'warn' if int(p.strip('%')) > 80 else 'ok'
        except Exception:
            return 'ok'
    aichat = 'ok'
    try:
        import urllib.request as u
        resp = u.urlopen('http://127.0.0.1:8000/api/health', timeout=5)
        aichat = 'ok' if b'ok' in resp.read() else 'warn'
    except Exception:
        aichat = 'warn'
    r = subprocess.run(['systemctl', '--user', 'is-active', 'hermes-gateway'], capture_output=True, text=True)
    gw = r.stdout.strip() or 'unknown'
    r2 = subprocess.run(['systemctl', '--user', 'is-active', 'mail-watcher'], capture_output=True, text=True)
    mw = r2.stdout.strip() or 'unknown'
    cells.append({'k': 'Watchdog', 'v': 'healthy', 'state': state})
    cells.append({'k': 'Agent gateway', 'v': gw, 'state': 'ok' if gw == 'active' else 'warn'})
    cells.append({'k': 'Mail watcher', 'v': mw, 'state': 'ok' if mw == 'active' else 'warn'})
    cells.append({'k': 'aichat', 'v': 'up' if aichat == 'ok' else 'down', 'state': aichat})
    cells.append({'k': 'Disk', 'v': disk_pct, 'state': vcls(disk_pct)})
    cells.append({'k': 'Memory', 'v': mem_pct, 'state': vcls(mem_pct)})
    # extras: backup age, uptime, load
    from pathlib import Path as _P
    bak = _P('/home/ben/.restic-last-ok')
    if bak.exists():
        age_h = (time.time() - bak.stat().st_mtime) / 3600
        cells.append({'k': 'Last backup', 'v': f'{int(age_h)}h ago', 'state': 'ok' if age_h < 30 else 'warn'})
    up = subprocess.run(['uptime', '-p'], capture_output=True, text=True).stdout.strip().replace('up ', '')
    cells.append({'k': 'Uptime', 'v': up or '?', 'state': 'ok'})
    ld = subprocess.run(['uptime'], capture_output=True, text=True).stdout
    load = ld.split('load average:')[-1].split(',')[0].strip() if 'load average:' in ld else '?'
    cells.append({'k': 'Load', 'v': load, 'state': 'ok'})
    return cells


def anki_pending():
    """Anki pending-pile stats from the laptop-pushed CSV."""
    csvp = Path('/home/ben/life/anki-pending.csv')
    if not csvp.exists():
        return {'current': None, 'history': [], 'decks': []}
    rows = {}
    for line in csvp.read_text().splitlines()[1:]:
        parts = line.split(',')
        if len(parts) < 3:
            continue
        date, deck, n = parts[0], parts[1], parts[2]
        rows.setdefault(date, {})[deck] = int(n) if n else 0
    dates = sorted(rows)
    if not dates:
        return {'current': None, 'history': [], 'decks': []}
    last = dates[-1]
    cur = rows[last].get('ALL')
    prev = rows[dates[-2]].get('ALL') if len(dates) > 1 else None
    diff = (cur - prev) if (cur is not None and prev is not None) else None
    # sparkline: weekly sampled ALL values
    hist = []
    step = max(1, len(dates) // 40)
    for d in dates[::step]:
        v = rows[d].get('ALL')
        if v is not None:
            hist.append({'d': d, 'v': v})
    if dates[-1] not in [h['d'] for h in hist]:
        hist.append({'d': dates[-1], 'v': cur})
    # per-deck latest
    decks = sorted(
        [(k, v) for k, v in rows[last].items() if k != 'ALL'],
        key=lambda kv: -kv[1])
    return {'current': cur, 'prev': prev, 'diff': diff,
            'date': last, 'history': hist, 'decks': decks}


def main():
    tpl = Path(TEMPLATE).read_text()
    data = {
        'updated': datetime.now(HKT).strftime('%Y-%m-%d %H:%M HKT'),
        'commitments': commitments(),
        'school_upcoming': school_upcoming(),
        'school': school_posts(),
        'captures': captures(),
        'email': email_highlights(),
        'subs': recurring(),
        'anki': anki_pending(),
        'infra': infra(),
    }
    out = tpl
    for key, val in data.items():
        out = out.replace('%' + key.upper() + '%', json.dumps(val, ensure_ascii=False))
    Path(OUT).write_text(out)
    print('status page written:', OUT)


if __name__ == '__main__':
    main()

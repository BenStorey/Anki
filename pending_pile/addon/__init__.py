#!/usr/bin/env python3
"""Pending Pile — Anki add-on.

Records the number of pending review cards (limits ignored) at the
start of each Anki day, gap-fills missed days exactly, shows a
yesterday-diff banner on the deck browser, and adds a deck-by-deck
history chart to the stats screen.

Read-only: never modifies the collection. All hooks are wrapped in
try/except; failures go to pending-pile.log next to this file.
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import sqlite3
import sys
import traceback

from aqt import gui_hooks, mw

# ---------------------------------------------------------------- paths

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(ADDON_DIR, "pending-pile.log")
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

sys.path.insert(0, ADDON_DIR)
import recon  # noqa: E402


def log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a") as f:
            f.write(f"{datetime.datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


def load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {"banner_enabled": True, "chart_decks": [], "csv_path": ""}


CONFIG = load_config()


def csv_path() -> str:
    """CSV lives next to the collection by default."""
    p = CONFIG.get("csv_path")
    if p:
        return p
    try:
        base = mw.col.path
        if base:
            return os.path.join(os.path.dirname(base), "pending-pile.csv")
    except Exception:
        pass
    return os.path.join(ADDON_DIR, "pending-pile.csv")


CSV_SCHEMA = ["date", "deck", "pending_review", "pending_learning",
              "pending_new", "source"]


# ----------------------------------------------------------- collection db

def readonly_db() -> sqlite3.Connection | None:
    """Read-only connection to the same collection file Anki has open.

    Safe: SQLite allows multiple readers; we never write.
    """
    try:
        path = mw.col.path
        uri = f"file:{path}?mode=ro&immutable=0"
        return sqlite3.connect(uri, uri=True)
    except Exception:
        log("readonly_db failed:\n" + traceback.format_exc())
        return None


# -------------------------------------------------------------- CSV I/O

def read_csv(path: str) -> list[dict]:
    try:
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []
    except Exception:
        log("read_csv failed:\n" + traceback.format_exc())
        return []


def append_csv(path: str, rows: list[dict]) -> None:
    try:
        exists = os.path.exists(path)
        with open(path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_SCHEMA)
            if not exists:
                w.writeheader()
            w.writerows(rows)
    except Exception:
        log("append_csv failed:\n" + traceback.format_exc())


# -------------------------------------------------------------- snapshot

def learning_new_counts(db: sqlite3.Connection) -> tuple[int, int]:
    """Pending day-learning and new card counts (logged as extra cols)."""
    N = recon.current_day(db)
    lrn = db.execute(
        "SELECT COUNT(*) FROM cards WHERE type=3 AND queue>=0 AND due<=?",
        (N,),
    ).fetchone()[0]
    new = db.execute(
        "SELECT COUNT(*) FROM cards WHERE type=0 AND queue>=0"
    ).fetchone()[0]
    return lrn, new


def write_today_snapshot() -> None:
    """Append today's per-deck pending rows (first-open-of-day wins)."""
    path = csv_path()
    rows = read_csv(path)
    today_date = datetime.date.today().isoformat()
    if rows and rows[-1]["date"] == today_date:
        return  # already snapshotted today
    db = readonly_db()
    if db is None:
        return
    try:
        last_date = rows[-1]["date"] if rows else None
        live = recon.live_pending(db)  # per-deck incl 'ALL'
        lrn, new = learning_new_counts(db)
        new_rows = []
        for deck, cnt in sorted(live.items()):
            new_rows.append({
                "date": today_date,
                "deck": deck,
                "pending_review": cnt,
                "pending_learning": lrn if deck == "ALL" else "",
                "pending_new": new if deck == "ALL" else "",
                "source": "live",
            })
        append_csv(path, new_rows)
        log(f"snapshot {today_date}: ALL={live.get('ALL')} (live)")
        _gapfill(last_date, today_date, db, path)
    finally:
        db.close()


def _gapfill(last_date: str | None, today_date: str,
             db: sqlite3.Connection, path: str) -> None:
    """Fill days between the last snapshot and today exactly.

    On no-open days R=0, so the reconstruction is pure revlog math via
    recon.reconstruct_series (start-of-day per-deck counts).
    If a gapfilled day disagrees with what the anchors pin, the next
    live snapshot self-corrects (live wins on overlap when merged).
    """
    if not last_date:
        return
    try:
        N_last = recon.date_day(db, last_date)
        N_today = recon.date_day(db, today_date)
    except Exception:
        log("gapfill date parse failed:\n" + traceback.format_exc())
        return
    if N_today - N_last <= 1:
        return  # no gap
    try:
        series = recon.reconstruct_series(db, N_last + 1, N_today - 1)
        lrn, new = learning_new_counts(db)
        new_rows = []
        for N, counts in sorted(series.items()):
            date = recon.day_date(db, N)
            for deck in sorted(counts):
                new_rows.append({
                    "date": date,
                    "deck": deck,
                    "pending_review": counts[deck],
                    "pending_learning": lrn if deck == "ALL" else "",
                    "pending_new": new if deck == "ALL" else "",
                    "source": "gapfill",
                })
        append_csv(path, new_rows)
        log(f"gapfilled {len(new_rows)} rows "
            f"({N_last + 1}..{N_today - 1})")
    except Exception:
        log("gapfill failed:\n" + traceback.format_exc())


# ------------------------------------------------------------- hooks

def on_collection_did_load(_col) -> None:
    try:
        write_today_snapshot()
    except Exception:
        log("on_collection_did_load failed:\n" + traceback.format_exc())


def on_sync_did_finish() -> None:
    try:
        write_today_snapshot()
    except Exception:
        log("on_sync_did_finish failed:\n" + traceback.format_exc())


def _latest_before_today(rows: list[dict]) -> dict | None:
    today = datetime.date.today().isoformat()
    for r in reversed(rows):
        if r["deck"] == "ALL" and r["date"] != today:
            return r
    return None


def _today_all(rows: list[dict]) -> dict | None:
    today = datetime.date.today().isoformat()
    for r in reversed(rows):
        if r["deck"] == "ALL" and r["date"] == today:
            return r
    return None


def on_deck_browser_will_render_content(_deck_browser, content) -> None:
    try:
        if not CONFIG.get("banner_enabled", True):
            return
        rows = read_csv(csv_path())
        today_row = _today_all(rows)
        if today_row is None:
            return
        n = int(today_row["pending_review"])
        y = _latest_before_today(rows)
        if y is None:
            banner = f"Pending pile: <b>{n:,}</b> review cards"
        else:
            diff = n - int(y["pending_review"])
            base = int(y["pending_review"])
            pct = (diff / base * 100) if base else 0
            sign = "+" if diff >= 0 else "\u2212"
            banner = (
                f"Pending pile: <b>{n:,}</b> review cards"
                f" &nbsp;—&nbsp; {y['date']}: {base:,}"
                f" ({sign}{abs(diff):,}, {sign}{abs(pct):.1f}%)"
            )
        content.stats += (
            f'<div style="text-align:center;font-size:1.1em;'
            f'margin:0.4em 0;">{banner}</div>'
        )
    except Exception:
        log("banner failed:\n" + traceback.format_exc())


# --------------------------------------------------------- stats chart

def build_svg(series: dict[str, list[tuple[str, int]]]) -> str:
    """Inline SVG: one line per top-level deck + bold ALL line."""
    if not series:
        return "<p>No pending-pile history yet.</p>"
    dates = sorted({d for pts in series.values() for d, _ in pts})
    if len(dates) < 2:
        return "<p>Not enough history yet.</p>"
    W, H = 1100, 420
    x0, x1 = 60, W - 140
    y0, y1 = H - 40, 20
    ymax = max(v for pts in series.values() for _, v in pts) or 1
    di = {d: i for i, d in enumerate(dates)}

    def xy(d: str, v: int) -> tuple[float, float]:
        x = x0 + (x1 - x0) * di[d] / (len(dates) - 1)
        y = y0 - (y0 - y1) * v / ymax
        return x, y

    colors = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
              "#edc949", "#af7aa1", "#ff9da7", "#9c755f"]
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px" '
             f'xmlns="http://www.w3.org/2000/svg">']
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        v = int(ymax * frac)
        y = y1 + (y0 - y1) * frac
        parts.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" '
                     f'stroke="#ccc" stroke-width="1"/>')
        parts.append(f'<text x="{x0 - 6}" y="{y + 4}" font-size="11" '
                     f'text-anchor="end">{v:,}</text>')
    for d in (dates[0], dates[len(dates) // 2], dates[-1]):
        x, _ = xy(d, 0)
        parts.append(f'<text x="{x}" y="{H - 20}" font-size="11" '
                     f'text-anchor="middle">{d}</text>')
    items = [(k, v) for k, v in series.items() if k != "ALL"]
    items.sort(key=lambda kv: -max(p[1] for p in kv[1]))
    for i, (deck, pts) in enumerate(items):
        color = colors[i % len(colors)]
        pl = " ".join(f"{xy(d, v)[0]:.1f},{xy(d, v)[1]:.1f}" for d, v in pts)
        last_d, last_v = pts[-1]
        lx, ly = xy(last_d, last_v)
        parts.append(f'<polyline points="{pl}" fill="none" '
                     f'stroke="{color}" stroke-width="1.4" opacity="0.85"/>')
        parts.append(f'<text x="{lx + 5}" y="{ly + 4}" font-size="11" '
                     f'fill="{color}">{deck}</text>')
    pts = series["ALL"]
    pl = " ".join(f"{xy(d, v)[0]:.1f},{xy(d, v)[1]:.1f}" for d, v in pts)
    parts.append(f'<polyline points="{pl}" fill="none" '
                 f'stroke="#222" stroke-width="2.6"/>')
    last_d, last_v = pts[-1]
    lx, ly = xy(last_d, last_v)
    parts.append(f'<text x="{lx + 5}" y="{ly + 4}" font-size="12" '
                 f'font-weight="bold">{last_v:,}</text>')
    parts.append("</svg>")
    return "".join(parts)


def on_stats_dialog_will_show(dialog) -> None:
    """Add a Pending Pile panel to the stats dialog.

    The modern stats dialog loads a sveltekit page which REPLACES the DOM
    after this hook fires, so we subscribe to the webview's loadFinished
    signal and inject once the page has actually rendered (with retries
    for the SPA's async mount).
    """
    try:
        web = getattr(getattr(dialog, "form", None), "web", None)
        if web is None:
            return

        from aqt.qt import QTimer

        attempts = {"n": 0}

        def inject() -> None:
            attempts["n"] += 1
            try:
                rows = read_csv(csv_path())
                if not rows:
                    return
                by_deck: dict[str, dict[str, int]] = {}
                for r in rows:
                    try:
                        by_deck.setdefault(r["deck"], {})[r["date"]] = int(
                            r["pending_review"]
                        )
                    except (ValueError, KeyError):
                        continue
                series = {
                    deck: sorted(dv.items()) for deck, dv in by_deck.items()
                }
                svg = build_svg(series)
                html = (
                    f'<div id="pendingpile" style="margin:1em;'
                    f'padding:0.5em 1em;">'
                    f'<h2 style="font-size:1.2em;margin:0.2em 0;">'
                    f'Pending Pile</h2>{svg}</div>'
                )
                import json as _json
                payload = _json.dumps(html)
                js = (
                    "var pp=document.getElementById('pendingpile');"
                    "if(!pp){"
                    "document.body.insertAdjacentHTML('afterbegin',"
                    + payload + ");"
                    "window.scrollTo(0,0);}"
                )
                web.eval(js)
                # a few retries in case the SPA mounts late
                if attempts["n"] < 5:
                    QTimer.singleShot(1500, inject)
            except Exception:
                log("stats chart inject failed:\n" + traceback.format_exc())

        # inject after the sveltekit page loads; also try immediately
        web.loadFinished.connect(inject)
        inject()
    except Exception:
        log("stats chart failed:\n" + traceback.format_exc())


# --------------------------------------------------------- init

_hooks_installed = False


def _install_hooks() -> None:
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True
    gui_hooks.collection_did_load.append(on_collection_did_load)
    gui_hooks.sync_did_finish.append(on_sync_did_finish)
    gui_hooks.deck_browser_will_render_content.append(
        on_deck_browser_will_render_content
    )
    gui_hooks.stats_dialog_will_show.append(on_stats_dialog_will_show)
    log("hooks installed")


def on_profile_did_open() -> None:
    try:
        gui_hooks.profile_did_open.remove(on_profile_did_open)
    except Exception:
        pass
    _install_hooks()
    try:
        write_today_snapshot()
    except Exception:
        log("initial snapshot failed:\n" + traceback.format_exc())


try:
    if mw.col is not None:
        # imported after profile load
        _install_hooks()
        write_today_snapshot()
    else:
        gui_hooks.profile_did_open.append(on_profile_did_open)
except Exception:
    log("module init failed:\n" + traceback.format_exc())

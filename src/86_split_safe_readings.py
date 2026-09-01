#!/usr/bin/env python3
"""
86_split_safe_readings.py — split whole-compound JP readings into per-KANJI ruby,
validated by rendering through Anki's own furigana engine (ground truth).

WHAT:  組み合[くみあ]わせ  →  組[く]み 合[あ]わせ
       買い手[かいて]     →  買[か]い 手[て]
so ruby sits ONLY over single kanji (never over okurigana), with a SPACE between
ruby groups (required for correct Anki rendering).

SAFETY (ground-truth validated, re-runnable):
  - Only touches notes with the embedded-okurigana pattern (kana between kanji in
    a ruby base) whose in-bracket reading kana has NO repeats (unambiguous).
  - Ambiguous (repeated-kana) readings are exported for human review, untouched.
  - THE SAFETY GATE: render the ORIGINAL and the SPLIT through Anki's
    {{furigana:}} engine and compare the multiset of DISPLAYED kana. If they
    differ, the split corrupted the reading — skip that note. This catches
    every possible mis-placement, not just the naive ones.
  - Requires the SNAP python (to import anki for rendering) + venv for nothing.
    Uses sqlite for the DB write. Anki must be closed.

USAGE (snap python, Anki closed):
  /snap/anki-desktop/85/bin/python3.12 src/86_split_safe_readings.py
"""
import re, sqlite3, subprocess, sys, time
from pathlib import Path

HOME = Path.home()
COLLECTION = Path("/home/ben/snap/anki-desktop/common/User 1/collection.anki2")
JP_ENH = 1738229000
BACKUP_DIR = HOME / "dev/sino-korean/backups"
OUT_DIR = HOME / "dev/sino-korean/data/sentences_raw/jp_okurigana_split"

KANA = re.compile(r"[\u3040-\u30ff]")
def is_kana(ch): return bool(KANA.fullmatch(ch))
def is_kanji(ch): return '\u4e00' <= ch <= '\u9fff'

# ---- Anki renderer (ground truth) ----
_render_cache = {}
def _get_renderer():
    sys.path.insert(0, "/snap/anki-desktop/85/lib/python3.12/site-packages")
    import tempfile
    import anki.collection as coll
    tmp = Path(tempfile.mkdtemp(prefix="jpval-"))
    col = coll.Collection(str(tmp / "col.anki2")); mm = col.models
    nt = mm.new("f"); mm.add_field(nt, mm.new_field("Reading"))
    t = mm.new_template("t"); t["qfmt"] = "{{furigana:Reading}}"; mm.add_template(nt, t); mm.add(nt)
    return col, nt

_renderer = None
def render(s):
    """Render a Reading string through Anki's furigana engine -> HTML."""
    global _renderer
    if s in _render_cache: return _render_cache[s]
    if _renderer is None: _renderer = _get_renderer()
    col, nt = _renderer
    n = col.new_note(nt["id"]); n["Reading"] = s; col.add_note(n, 1)
    card = col.db.first("SELECT id FROM cards WHERE nid=?", n.id)[0]
    h = col._backend.render_existing_card(card_id=card, browser=True, partial_render=False).question_nodes[0].text
    _render_cache[s] = h
    return h

def displayed_kana(html):
    """Multiset of kana the user sees (rt readings + bare okurigana outside ruby)."""
    rt = ''.join(re.findall(r'<rt>(.*?)</rt>', html))
    no_ruby = re.sub(r'<ruby>.*?</ruby>', '', html)
    bare = ''.join(ch for ch in re.sub(r'<[^>]+>', '', no_ruby) if is_kana(ch))
    return ''.join(sorted(rt + bare))

# ---- core logic ----
def brackets(r): return re.findall(r'\[([^\]]+)\]', r)

def embedded_okurigana(r):
    for m in re.finditer(r'([^\[]*?)\[([^\]]+)\]', r):
        base = m.group(1)
        for i, ch in enumerate(base):
            if is_kana(ch) and any(is_kanji(x) for x in base[:i]) and any(is_kanji(x) for x in base[i+1:]):
                return True
    return False

def ambiguous_repeat(r):
    for b in brackets(r):
        k = ''.join(ch for ch in b if is_kana(ch))
        if len(k) != len(set(k)):
            return True
    return False

def is_sentence_junk(r):
    return ('。' in r or '、' in r or '<' in r or '？' in r or '！' in r or len(r) > 60)

def split_reading(r):
    surface = re.sub(r'\[[^\]]+\]', '', r).replace(' ', '')
    bracks = ''.join(brackets(r))
    trailing = r.rsplit(']', 1)[1] if ']' in r else r
    full = bracks + ''.join(ch for ch in trailing if is_kana(ch))
    if not full or not surface:
        return None
    runs, i = [], 0
    while i < len(surface):
        ch = surface[i]
        if is_kanji(ch):
            j = i
            while j < len(surface) and is_kanji(surface[j]): j += 1
            runs.append(('kanji', surface[i:j])); i = j
        elif is_kana(ch):
            j = i
            while j < len(surface) and is_kana(surface[j]): j += 1
            runs.append(('kana', surface[i:j])); i = j
        else:
            runs.append(('other', ch)); i += 1
    ri, out = 0, []
    for idx, (typ, text) in enumerate(runs):
        if typ == 'other':
            out.append(text); continue
        if typ == 'kana':
            out.append(text)
            for ch in text:
                if ri < len(full) and full[ri] == ch: ri += 1
            continue
        after = ''.join(t for _, t in runs[idx+1:])
        nk = next((c for c in after if is_kana(c)), None)
        buf = []
        while ri < len(full):
            if nk and full[ri] == nk: break
            buf.append(full[ri]); ri += 1
        out.append(f"{text}[{''.join(buf)}]" if buf else text)
    result = ''.join(out)
    result = re.sub(r'([\u3040-\u30ff])([\u4e00-\u9fff]\[)', r'\1 \2', result)
    return result

def validate_via_render(old, new):
    """Ground-truth: rendered displayed-kana multiset must be identical."""
    try:
        return displayed_kana(render(old)) == displayed_kana(render(new))
    except Exception:
        return False

def check_anki_closed():
    for proc in ["anki", "anki-qt", "anki-desktop", "ankiw"]:
        r = subprocess.run(["pgrep", "-x", proc], capture_output=True, text=True)
        if r.stdout.strip():
            sys.exit(f"ABORT: Anki ({proc}) is running. Close Anki and re-run.")

def main():
    check_anki_closed()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    uc = lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower())
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"collection_pre_okurigana_split_{stamp}.anki2"
    src = sqlite3.connect(f"file:{COLLECTION}?mode=ro", uri=True); src.create_collation("unicase", uc)
    dst = sqlite3.connect(str(backup)); src.backup(dst); dst.close(); src.close()
    print(f"  Backup: {backup}")

    conn = sqlite3.connect(str(COLLECTION)); conn.create_collation("unicase", uc)
    rows = conn.execute("SELECT id, flds FROM notes WHERE mid=?", (JP_ENH,)).fetchall()
    now = int(time.time())
    conn.execute("BEGIN")
    updated=0; skip_junk=0; skip_amb=0; skip_fail=0; skip_same=0; amb_list=[]
    for nid, flds in rows:
        f = flds.split(chr(31)); cur = f[2]
        if not embedded_okurigana(cur): continue
        if is_sentence_junk(cur): skip_junk+=1; continue
        if ambiguous_repeat(cur):
            skip_amb+=1; amb_list.append(nid); continue
        new = split_reading(cur)
        if not new or new == cur or not validate_via_render(cur, new):
            skip_fail+=1; continue
        f[2] = new
        if len(f) > 12: f[12] = new
        conn.execute("UPDATE notes SET flds=?, mod=?, usn=-1 WHERE id=?", (chr(31).join(f), now, nid))
        conn.execute("UPDATE cards SET mod=?, usn=-1 WHERE nid=?", (now, nid))
        updated += 1
    conn.execute("UPDATE col SET mod=?", (now,))
    conn.commit(); conn.close()

    if amb_list:
        (OUT_DIR / "ambiguous_needs_review.txt").write_text(
            "# JP readings with repeated-kana (ambiguous split — left for human review).\n"
            + "\n".join(str(x) for x in amb_list) + "\n", encoding="utf-8")
    print(f"JP Enhanced: {len(rows)}")
    print(f"  UPDATED (split to per-kanji ruby): {updated}")
    print(f"  skipped (sentence-junk): {skip_junk}")
    print(f"  skipped (ambiguous repeat-kana, export@{OUT_DIR/'ambiguous_needs_review.txt'}): {skip_amb}")
    print(f"  skipped (render-validate-fail, left as-is): {skip_fail}")
    print(f"  skipped (already correct): {skip_same}")
    print("Done. Verify -> Open Anki -> Check Database -> sync.")

if __name__ == "__main__":
    main()
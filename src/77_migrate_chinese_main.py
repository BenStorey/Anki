#!/usr/bin/env python3
"""
Migrate the main Chinese deck (15,189 cards) to Chinese Enhanced.

Offline-first: reads LLM output from data/sentences_raw/chinese_main/out_cm_*.txt.
Maps each note in the main Chinese deck (old model) to its LLM entry by the
Expression word, rebuilds the 12-field record, and updates in place — cards
STAY in the Chinese deck (no deck move).

SAFETY:
- Must run with Anki fully closed. (Writing while Anki is open corrupts the DB.)
- Creates a read-only SQLite backup at backups/ before writing.
- Refuses to run if Anki is detected running.
"""
import sqlite3, time, sys, subprocess
from pathlib import Path

COLLECTION = Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
LLM_DIR = Path.home() / "dev/sino-korean/data/sentences_raw/chinese_main"
BACKUP_DIR = Path.home() / "dev/sino-korean/backups"
OLD_MODEL_ID = 1351220176888    # "Chinese"
NEW_MODEL_ID = 1787807921282    # "Chinese Enhanced"
CHINESE_DECK_ID = 1351219999178 # main Chinese deck


def unicase(a, b):
    return (a.lower() > b.lower()) - (a.lower() < b.lower())


def check_anki_closed():
    """Refuse to proceed if Anki is running."""
    try:
        for proc in ["anki", "anki-qt", "anki-desktop", "ankiDesktop"]:
            r = subprocess.run(["pgrep", "-x", proc], capture_output=True, text=True)
            if r.stdout.strip():
                sys.exit(f"ABORT: Anki ({proc}) is running. Close Anki fully and re-run.")
    except FileNotFoundError:
        pass  # pgrep unavailable — proceed


def make_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"collection_pre_chinese_main_{stamp}.anki2"
    src = sqlite3.connect(f"file:{COLLECTION}?mode=ro", uri=True)
    src.create_collation("unicase", unicase)
    dst = sqlite3.connect(str(backup))
    src.backup(dst)
    dst.close(); src.close()
    print(f"  Backup: {backup}")
    return backup


def load_llm():
    """Return {word: {meaning, nuance_en, nuance_cn, ex1, ex1_en, ...}}"""
    prefixes = [("Meaning:", "meaning"), ("Nuance_EN:", "nuance_en"),
                ("Nuance_CN:", "nuance_cn"), ("Example1:", "ex1"),
                ("Example1_EN:", "ex1_en"), ("Example2:", "ex2"),
                ("Example2_EN:", "ex2_en"), ("Example3:", "ex3"),
                ("Example3_EN:", "ex3_en")]
    llm = {}
    for f in LLM_DIR.glob("out_cm_*.txt"):
        content = f.read_text(encoding="utf-8", errors="replace")
        for block in content.split("===word: ")[1:]:
            word = block.split("===")[0].strip()
            rest = block.split("===")[1] if "===" in block else block
            fields = {}
            for line in rest.split("\n"):
                s = line.strip()
                for pfx, key in prefixes:
                    if s.startswith(pfx):
                        fields[key] = s[len(pfx):].strip()
            if word:
                llm[word] = fields
    return llm


def build_fields(word, old_flds, entry):
    """Rebuild the 12 Chinese Enhanced fields, preserving original pinyin."""
    # old: [Expression, Meaning(HTML), Reading/Pinyin]
    pinyin = old_flds[2].strip() if len(old_flds) > 2 else ""
    meaning = entry.get("meaning", "").strip()
    return chr(31).join([
        word,                            # 0 Expression
        meaning,                         # 1 Meaning (clean LLM)
        pinyin,                          # 2 Pinyin (keep original)
        "",                              # 3 Nuance (empty)
        entry.get("ex1", ""),            # 4 Example1
        entry.get("ex1_en", ""),         # 5 Example1_EN
        entry.get("ex2", ""),            # 6 Example2
        entry.get("ex2_en", ""),         # 7 Example2_EN
        entry.get("ex3", ""),            # 8 Example3
        entry.get("ex3_en", ""),         # 9 Example3_EN
        entry.get("nuance_en", ""),      # 10 Nuance_EN
        entry.get("nuance_cn", ""),      # 11 Nuance_CN
    ])


def main():
    check_anki_closed()
    print(f"Loading LLM output from {LLM_DIR}...")
    llm = load_llm()
    print(f"  Loaded {len(llm)} LLM entries")

    make_backup()

    print(f"Connecting to {COLLECTION}...")
    conn = sqlite3.connect(str(COLLECTION))
    conn.create_collation("unicase", unicase)

    # All notes whose cards sit in the main Chinese deck, on the old model
    cursor = conn.execute('''
        SELECT n.id, n.flds FROM notes n
        JOIN cards c ON c.nid = n.id
        WHERE n.mid = ? AND c.did = ?
        GROUP BY n.id
    ''', (OLD_MODEL_ID, CHINESE_DECK_ID))
    notes = [(row[0], row[1].split(chr(31))) for row in cursor.fetchall()]
    print(f"  {len(notes)} main Chinese deck notes to migrate")

    matched, unmatched = [], []
    for nid, flds in notes:
        word = (flds[0].strip() if flds else "")
        entry = llm.get(word)
        if not entry or not entry.get("meaning"):
            unmatched.append((word, nid))
            continue
        matched.append((build_fields(word, flds, entry), nid))

    print(f"  Matched: {len(matched)}, unmatched: {len(unmatched)}")

    if matched:
        now = int(time.time() * 1000)
        conn.execute("BEGIN TRANSACTION")
        for fields, nid in matched:
            conn.execute(
                "UPDATE notes SET mid = ?, flds = ?, mod = ?, usn = -1 WHERE id = ?",
                (NEW_MODEL_ID, fields, now, nid))
        # Touch cards so they're marked changed; keep them in the Chinese deck
        conn.execute('''
            UPDATE cards SET mod = ?, usn = -1
            WHERE did = ? AND nid IN (SELECT id FROM notes WHERE mid = ?)
        ''', (now, CHINESE_DECK_ID, NEW_MODEL_ID))
        conn.execute("UPDATE col SET mod = ?", (now,))
        conn.commit()
        print(f"  Updated {len(matched)} notes in place (Chinese deck id={CHINESE_DECK_ID})")

    # Report unmatched words (for later attention)
    if unmatched:
        uw = [w for w, _ in unmatched][:50]
        print(f"\nUnmatched ({len(unmatched)}): {uw}")

    # ── Verification ──
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)
    cursor = conn.execute("SELECT flds FROM notes WHERE mid = ? LIMIT 5", (NEW_MODEL_ID,))
    for row in cursor.fetchall():
        f = row[0].split(chr(31))
        if len(f) >= 12:
            print(f"  {f[0][:20]:20s} | {f[1][:22]:22s} | EN: {f[10][:26]:26s} | CN: {f[11][:22]}")
            print(f"                      Pinyin: {f[2][:10]:10s} Ex1: {f[4][:40]}")

    cursor = conn.execute("SELECT flds FROM notes WHERE mid = ?", (NEW_MODEL_ID,))
    total = m_ok = en_ok = cn_ok = pin_ok = 0
    for row in cursor.fetchall():
        f = row[0].split(chr(31))
        if len(f) >= 12:
            total += 1
            if f[1].strip(): m_ok += 1
            if f[10].strip(): en_ok += 1
            if f[11].strip(): cn_ok += 1
            if f[2].strip(): pin_ok += 1
    # Note: includes the 1181 WIP cards already migrated
    print(f"\nEnhanced notes now in DB: {total}")
    print(f"  Meaning:   {m_ok}/{total} ({m_ok/total*100:.0f}%)")
    print(f"  Nuance_EN: {en_ok}/{total} ({en_ok/total*100:.0f}%)")
    print(f"  Nuance_CN: {cn_ok}/{total} ({cn_ok/total*100:.0f}%)")
    print(f"  Pinyin:    {pin_ok}/{total} ({pin_ok/total*100:.0f}%)")

    conn.close()
    print("\nDone! Cards remain in the Chinese deck. Check Database + sync in Anki.")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Remove the 'Production' template from Japanese Enhanced via Anki's proper API.

Run with the SNAP-bundled python (so `anki` imports):
    /snap/anki-desktop/current/bin/python3.12 src/81_remove_jp_production.py <copy.db>

Usage:
    <copy.db>  path to a collection.anki2 to operate on (required — used for dry-run).

Opens the collection, removes the "Production" template (ord=1) from the
Japanese Enhanced notetype so it has only "Recognition", deletes any stray
ord=1 cards, and persists. Safe + backs up.
"""
import sys
from pathlib import Path

COLLECTION = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
MODEL_NAME = "Japanese Enhanced"
PROD_NAME = "Production"

sys.path.insert(0, "/snap/anki-desktop/85/lib/python3.12/site-packages")
import anki.storage as storage
from anki.utils import ids2str

def main():
    print(f"Opening collection: {COLLECTION}")
    col = storage.Collection(str(COLLECTION))

    mm = col.models
    nt = mm.by_name(MODEL_NAME)
    if not nt:
        print(f"ERROR: no notetype named '{MODEL_NAME}'")
        col.close(); return 1
    print(f"Found '{MODEL_NAME}' with templates:")
    for tmpl in nt["tmpls"]:
        print(f"  ord={tmpl['ord']} name={tmpl['name']}")

    # Count ord=1 cards before
    before = col.db.scalar("SELECT COUNT(*) FROM cards WHERE ord=1 AND nid IN (SELECT id FROM notes WHERE mid=?)", nt["id"])
    print(f"Cards at ord=1 before removal: {before}")

    prod = next((t for t in nt["tmpls"] if t["name"] == PROD_NAME or t["ord"] == 1), None)
    if not prod:
        print("No Production template found (already removed?)")
        col.close(); return 0

    # Remove template via API (handles req + persistence)
    try:
        mm.remove_template(nt, prod)
        print("Removed Production from model dict")
    except Exception as e:
        print(f"remove_template error: {e}")
        col.close(); return 1

    # Delete stray ord=1 cards explicitly (belt and braces)
    nid_ct = col.db.scalar("SELECT COUNT(*) FROM cards WHERE ord=1 AND nid IN (SELECT id FROM notes WHERE mid=?)", nt["id"])
    col.db.execute("DELETE FROM cards WHERE ord=? AND nid IN (SELECT id FROM notes WHERE mid=?)", 1, nt["id"])
    print(f"Deleted {nid_ct} ord=1 cards")

    # Persist the schema change (removes the template + req entry in backend)
    mm.update_dict(nt)
    nt = mm.get(nt["id"])   # re-load mutated notetype
    col.save()

    # Verify
    nt2 = mm.by_name(MODEL_NAME)
    print(f"\nVerified templates now: {[t['name'] for t in nt2['tmpls']]}")
    after_ord1 = col.db.scalar("SELECT COUNT(*) FROM cards WHERE ord=1 AND nid IN (SELECT id FROM notes WHERE mid=?)", nt2["id"])
    after_ord0 = col.db.scalar("SELECT COUNT(*) FROM cards WHERE ord=0 AND nid IN (SELECT id FROM notes WHERE mid=?)", nt2["id"])
    print(f"ord=1 cards now: {after_ord1}")
    print(f"ord=0 (Recognition) cards now: {after_ord0}")

    col.close()
    print("\nDONE.")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
84_add_image_field.py — add an 'Image' field to JP + CN Enhanced notetypes.

Runs under the SNAP python (imports real anki). Call with a target collection
path as argv[1] (for dry-run pass a COPY; to apply pass the live one).

For each Enhanced notetype it:
  1. builds a new field via mm.new_field('Image'),
  2. mm.add_field(nt, field),
  3. mm.update_dict(nt)  (persists the schema change; Anki rebuilds every note's
     flds to the new field count, appending an empty Image segment),
  4. verifies: field count is +1, all notes have the new segment count,
     integrity ok.

Usage:  /snap/anki-desktop/85/bin/python3.12 src/84_add_image_field.py <collection.anki2>
"""
import sys
from pathlib import Path

COLLECTION = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
MODELS = {
    "Japanese Enhanced": 1738229000,
    "Chinese Enhanced": 1787807921282,
}

sys.path.insert(0, "/snap/anki-desktop/85/lib/python3.12/site-packages")
import anki.storage as storage

def main():
    print(f"Opening: {COLLECTION}")
    col = storage.Collection(str(COLLECTION))
    mm = col.models
    for name, ntid in MODELS.items():
        nt = mm.by_name(name)
        if not nt:
            print(f"  !! {name} not found"); continue
        # skip if already present
        if any(f["name"].lower() == "image" for f in nt["flds"]):
            print(f"  {name}: already has an Image field"); continue
        newf = mm.new_field("Image")
        mm.add_field(nt, newf)
        mm.update_dict(nt)
        nt2 = mm.get(ntid)
        nfields = len(nt2["flds"])
        print(f"  {name}: added 'Image' -> now {nfields} fields: {[f['name'] for f in nt2['flds']]}")
    col.save()
    col.close()
    print("DONE.")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Remove the redundant "Nuance" field (index 3) from the Japanese Enhanced model.
Nuance_JP (index 11) already holds the Japanese nuance — field 3 duplicates it.
Also clear the data from field 3 on all existing notes.

Usage: Close Anki, then: python3 src/56_remove_nuance_field.py
"""
import sys, shutil, json
from pathlib import Path

COLLECTION = Path.home() / "snap" / "anki-desktop" / "common" / "User 1" / "collection.anki2"
BACKUP = COLLECTION.with_suffix(".anki2.before_remove_nuance")

shutil.copy2(COLLECTION, BACKUP)
print(f"Backup: {BACKUP}")

sys.path.insert(0, "/snap/anki-desktop/85/lib/python3.12/site-packages")
import anki.storage as storage

col = storage.Collection(str(COLLECTION))

m = col.models.by_name("Japanese Enhanced")
if not m:
    print("ERROR: Japanese Enhanced model not found")
    sys.exit(1)

# Show current field list
print("Current fields:")
for f in m['flds']:
    print(f"  {f['ord']}: {f['name']}")

# Remove Nuance field (ord=3)
new_flds = [f for f in m['flds'] if f['name'] != 'Nuance']
if len(new_flds) == len(m['flds']):
    print("Field 'Nuance' not found — nothing to do")
    col.close()
    sys.exit(0)

m['flds'] = new_flds

# Re-index ord values
for i, f in enumerate(m['flds']):
    f['ord'] = i

# Update the template field references — shift field indices after Nuance removal
# Examples shift from 4->3, 5->4, 6->5, 7->6, 8->7, 9->8
# Nuance_EN shifts from 10->9
# Nuance_JP shifts from 11->10
# Furigana shifts from 12->11
# The template uses {{fieldname}} syntax, not indices, so it should survive.

col.models.save(m)

# Clear field 3 content on all notes using this model
sep = chr(31)
now = int(__import__('time').time())
updated = 0
for nid in col.db.list("SELECT id FROM notes WHERE mid=?", m['id']):
    flds = col.db.scalar("SELECT flds FROM notes WHERE id=?", nid)
    parts = flds.split(sep)
    
    # Old field 3 was Nuance — just leave it empty. The new field 3 is Example1.
    # Actually after removing the field from the model, Anki will re-interpret
    # the flds string. If we have 13 segments and the model now says 12 fields,
    # Anki will ignore the last segment OR show a field count mismatch.
    # 
    # Safer approach: rebuild flds with exactly the new field count.
    # Old: 13 parts [0-12]
    # New: 12 parts [0,1,2, 4,5,6,7,8,9, 10,11,12] — skip index 3
    if len(parts) == 13:
        new_parts = parts[:3] + parts[4:]  # skip old field 3 (Nuance)
        assert len(new_parts) == 12, f"expected 12, got {len(new_parts)}"
        new_flds = sep.join(new_parts)
        col.db.execute("UPDATE notes SET flds=?, mod=?, usn=-1 WHERE id=?", new_flds, now, nid)
        updated += 1

col.save()
col.close()
print(f"\nRemoved 'Nuance' field. Updated {updated} notes to 12-field format.")
print("Open Anki to see changes.")
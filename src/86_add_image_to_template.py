#!/usr/bin/env python3
"""
86_add_image_to_template.py — render {{Image}} at the top of the BACK card, conditionally.

For JP + CN Enhanced Recognition template, insert above the Meaning block:
    {{#Image}}<div class="card-image">{{Image}}</div>{{/Image}}

Runs under snap python (real anki API) so the template change is safe + persisted.

Usage: x src/86_add_image_to_template.py <collection.anki2>
"""
import sys
from pathlib import Path

COLLECTION = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    Path.home() / "snap/anki-desktop/common/User 1/collection.anki2"
MODELS = {"Japanese Enhanced": 1738229000, "Chinese Enhanced": 1787807921282}

# Marker to append right before the Meaning block on the BACK (afmt).
# We insert after the frontbg back div closes and before <span class="en">.
IMAGE_HTML = '\n  {{#Image}}<div class="card-image">{{Image}}</div>{{/Image}}'

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
        tmpl = nt["tmpls"][0]
        afmt = tmpl["afmt"]
        if "{{#Image}}" in afmt:
            print(f"  {name}: template already has {{Image}}"); continue
        # Find the back content: insert the Image block just before {{Meaning}}
        # (works for both JP which has "<span class=en>{{Meaning}}" and CN "\t{{Meaning}}").
        target = "{{Meaning}}"
        if target in afmt:
            newafmt = afmt.replace(target, IMAGE_HTML.replace("\n  ", " ") + " " + target, 1)
        else:
            print(f"  !! {name}: could not find {{Meaning}} anchor"); continue
        tmpl["afmt"] = newafmt
        mm.update_dict(nt)
        print(f"  {name}: added {{#Image}} to back template")
    col.save()
    col.close()
    print("DONE.")

if __name__ == "__main__":
    main()
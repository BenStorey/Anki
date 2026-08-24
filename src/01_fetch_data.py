#!/usr/bin/env python3
"""
Phase 1: Download all raw data sources for the Sino-Korean Anki deck generator.
"""
import os
import sys
import time
import requests
from pathlib import Path
from tqdm import tqdm

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "kengdic.tsv": {
        "url": "https://raw.githubusercontent.com/garfieldnate/kengdic/master/kengdic.tsv",
        "desc": "Korean-English dictionary with hanja",
    },
    "hanja.txt": {
        "url": "https://raw.githubusercontent.com/bekker/hanja-rs/master/data/hanja.txt",
        "desc": "Hangul↔Hanja character mapping (303K pairs)",
    },
    "jmdict-eng-common.zip": {
        "url": None,  # resolved dynamically below
        "desc": "JMdict English-Common JSON (to be resolved via GitHub API)",
    },
    "kor_sentences.tsv.bz2": {
        "url": "https://downloads.tatoeba.org/exports/per_language/kor/kor_sentences.tsv.bz2",
        "desc": "Tatoeba Korean sentences",
    },
    "jpn_sentences.tsv.bz2": {
        "url": "https://downloads.tatoeba.org/exports/per_language/jpn/jpn_sentences.tsv.bz2",
        "desc": "Tatoeba Japanese sentences",
    },
    "cmn_sentences.tsv.bz2": {
        "url": "https://downloads.tatoeba.org/exports/per_language/cmn/cmn_sentences.tsv.bz2",
        "desc": "Tatoeba Mandarin Chinese sentences",
    },
    "eng_sentences.tsv.bz2": {
        "url": "https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2",
        "desc": "Tatoeba English sentences",
    },
    "links.tar.bz2": {
        "url": "https://downloads.tatoeba.org/exports/links.tar.bz2",
        "desc": "Tatoeba sentence cross-links (EN/KO/JA/ZH sentence IDs)",
    },
}


def resolve_jmdict_url():
    """Fetch the latest jmdict-simplified release and find the eng-common ZIP."""
    api = "https://api.github.com/repos/scriptin/jmdict-simplified/releases/latest"
    resp = requests.get(api, timeout=30)
    resp.raise_for_status()
    for asset in resp.json().get("assets", []):
        name = asset["name"]
        if "jmdict-eng-common" in name and name.endswith(".json.zip"):
            return asset["browser_download_url"]
    raise RuntimeError("Could not find jmdict-eng-common ZIP in latest release")


def download_file(url, dest, desc=""):
    """Download a file with progress bar."""
    if not url:
        return False
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  ✓ {dest.name} — already exists ({dest.stat().st_size / 1e6:.1f} MB)")
        return True

    print(f"  ↓ {dest.name} — {desc}")
    try:
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with open(dest, "wb") as f, tqdm(
            desc=dest.name, total=total, unit="B", unit_scale=True, leave=False
        ) as pbar:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
                pbar.update(len(chunk))
        print(f"    ✓ {dest.name} — {dest.stat().st_size / 1e6:.1f} MB")
        return True
    except Exception as e:
        print(f"    ✗ {dest.name} — {e}")
        return False


def download_cedict():
    """Download CC-CEDICT. Try multiple mirrors."""
    dest = RAW_DIR / "cedict_ts.u8"
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  ✓ cedict_ts.u8 — already exists ({dest.stat().st_size / 1e6:.1f} MB)")
        return True

    urls = [
        "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz",
    ]

    for url in urls:
        print(f"  ↓ cedict.txt — trying {url}")
        try:
            resp = requests.get(url, stream=True, timeout=120)
            if resp.status_code != 200:
                continue
            resp.raise_for_status()
            # Decompress .gz in-memory
            import gzip
            raw = gzip.decompress(resp.content)
            dest.write_bytes(raw)
            print(f"    ✓ cedict.txt — {dest.stat().st_size / 1e6:.1f} MB")
            return True
        except Exception as e:
            print(f"    ✗ from {url}: {e}")
            continue

    print("    ✗ Could not download CC-CEDICT from any mirror")
    return False


def main():
    print("=" * 60)
    print("Phase 1: Data Fetcher — Sino-Korean Anki Deck")
    print("=" * 60)
    print()

    # Resolve JMdict URL
    print("[JMdict] Resolving latest release URL...")
    try:
        jmdict_url = resolve_jmdict_url()
        SOURCES["jmdict-eng-common.zip"]["url"] = jmdict_url
        print(f"  → {jmdict_url.split('/')[-1]}")
    except Exception as e:
        print(f"  ✗ Could not resolve JMdict URL: {e}")

    print()

    # Download all sources
    results = []
    for name, info in SOURCES.items():
        if name == "jmdict-eng-common.zip" and not info["url"]:
            print(f"  - {name} — skipped (URL not available)")
            results.append(False)
        else:
            ok = download_file(info["url"], RAW_DIR / name, info["desc"])
            results.append(ok)
        # Be polite to servers
        time.sleep(0.5)

    print()
    print("─" * 60)

    # Download CC-CEDICT separately
    cedict_ok = download_cedict()

    print("─" * 60)
    print()
    total = len(results) + 1
    success = sum(1 for r in results if r) + (1 if cedict_ok else 0)
    print(f"Downloaded {success}/{total} sources successfully.")

    missing = []
    if not results[0]: missing.append("kengdic.tsv")
    if not results[1]: missing.append("hanja.txt")
    if not results[2]: missing.append("jmdict-eng-common.zip")
    if not results[3]: missing.append("kor_sentences.tsv.bz2")
    if not cedict_ok: missing.append("cedict_ts.u8")
    if any(not r for r in results[4:]):
        for name, ok in zip(list(SOURCES.keys())[3:], results[3:]):
            if not ok:
                missing.append(name)

    if missing:
        print(f"\nMissing ({len(missing)}): {', '.join(missing)}")
        sys.exit(1)
    else:
        print("\nAll sources ready. Proceed to Phase 2: Cross-reference.")
        sys.exit(0)


if __name__ == "__main__":
    main()
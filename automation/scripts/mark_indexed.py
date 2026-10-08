#!/usr/bin/env python3
"""
Marque les URLs comme indexées dans GSC.
Utilisation : python3 mark_indexed.py https://audiobooklab.fr/blog-audiobook/slug1.html https://...
"""

import os
import json
import sys

INDEXED_FILE = "automation/state/indexed_urls.json"

def load_indexed():
    """Charge la liste des URLs déjà indexées."""
    if os.path.exists(INDEXED_FILE):
        with open(INDEXED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_indexed(indexed):
    """Sauvegarde la liste des URLs indexées."""
    os.makedirs(os.path.dirname(INDEXED_FILE), exist_ok=True)
    with open(INDEXED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(indexed)), f, ensure_ascii=False, indent=2)

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 mark_indexed.py <url1> <url2> ...")
        print("Exemple: python3 mark_indexed.py https://audiobooklab.fr/blog-audiobook/slug.html")
        sys.exit(1)

    indexed = load_indexed()
    urls = sys.argv[1:]

    for url in urls:
        if url in indexed:
            print(f"✅ Déjà indexée : {url}")
        else:
            indexed.add(url)
            print(f"✔️  Marquée comme indexée : {url}")

    save_indexed(indexed)
    print(f"\n✅ {len(urls)} URL(s) marquée(s) comme indexées.")

if __name__ == "__main__":
    main()

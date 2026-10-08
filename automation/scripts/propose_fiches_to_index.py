#!/usr/bin/env python3
"""
Propose les 5 dernières fiches non indexées dans Google Search Console.
À lancer quotidiennement pour obtenir les URLs à indexer.
"""

import os
import json
from datetime import datetime
from pathlib import Path

FICHES_DIR = "pages/moteur-audiobook"
SITE_BASE_URL = "https://audiobooklab.fr/blog-audiobook/"
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

def get_5_fiches_to_index():
    """Retourne les 5 dernières fiches HTML non indexées avec leurs URLs exactes."""

    if not os.path.isdir(FICHES_DIR):
        print("❌ Dossier de fiches non trouvé")
        return []

    # Lister tous les fichiers HTML (excl. sitemap, robots, etc.)
    fiche_files = sorted(
        [f for f in os.listdir(FICHES_DIR) if f.endswith(".html") and f not in ["sitemap.xml", "robots-fragment.txt"]],
        key=lambda f: os.path.getmtime(os.path.join(FICHES_DIR, f)),
        reverse=True  # Plus récents en premier
    )

    indexed = load_indexed()
    to_propose = []

    for filename in fiche_files:
        slug = filename[:-5]  # Enlever .html
        url = f"{SITE_BASE_URL}{slug}.html"

        if url not in indexed:
            to_propose.append({
                "slug": slug,
                "url": url,
                "filename": filename,
                "mtime": datetime.fromtimestamp(os.path.getmtime(os.path.join(FICHES_DIR, filename)))
            })

        if len(to_propose) >= 5:
            break

    return to_propose

def main():
    print("=" * 80)
    print(f"📋 FICHES À INDEXER - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 80)

    fiches = get_5_fiches_to_index()

    if not fiches:
        print("✅ Toutes les fiches sont déjà indexées !")
        return

    print(f"\n🎯 {len(fiches)} fiche(s) à indexer dans Google Search Console :\n")

    for i, fiche in enumerate(fiches, 1):
        print(f"{i}. {fiche['url']}")

    print(f"\n💡 Une fois indexées, marque-les comme validées avec :")
    print(f"   python3 automation/scripts/mark_indexed.py")

if __name__ == "__main__":
    main()

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
PROPOSED_HISTORY_FILE = "automation/state/proposed_history.json"

def load_proposed_history():
    """Charge la liste des URLs déjà proposées (jamais les reproposer)."""
    if os.path.exists(PROPOSED_HISTORY_FILE):
        with open(PROPOSED_HISTORY_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_proposed_history(proposed):
    """Sauvegarde la liste des URLs déjà proposées."""
    os.makedirs(os.path.dirname(PROPOSED_HISTORY_FILE), exist_ok=True)
    with open(PROPOSED_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(proposed)), f, ensure_ascii=False, indent=2)

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

    proposed_history = load_proposed_history()
    to_propose = []

    for filename in fiche_files:
        slug = filename[:-5]  # Enlever .html
        url = f"{SITE_BASE_URL}{slug}.html"

        if url not in proposed_history:
            to_propose.append({
                "slug": slug,
                "url": url,
                "filename": filename,
                "mtime": datetime.fromtimestamp(os.path.getmtime(os.path.join(FICHES_DIR, filename)))
            })

        if len(to_propose) >= 5:
            break

    # Enregistrer ces 5 fiches dans l'historique (jamais les reproposer)
    for fiche in to_propose:
        proposed_history.add(fiche["url"])
    save_proposed_history(proposed_history)

    return to_propose

def main():
    print("=" * 80)
    print(f"📋 FICHES À INDEXER - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 80)

    fiches = get_5_fiches_to_index()

    if not fiches:
        print("✅ Aucune nouvelle fiche à proposer (toutes les fiches ont déjà été proposées).")
        return

    print(f"\n🎯 {len(fiches)} fiche(s) À INDEXER :\n")

    for i, fiche in enumerate(fiches, 1):
        print(f"{i}. {fiche['url']}")

    print(f"\n🔍 Lien GSC : https://search.google.com/u/1/search-console/performance/search-analytics?resource_id=sc-domain%3Aaudiobooklab.fr")

if __name__ == "__main__":
    main()
